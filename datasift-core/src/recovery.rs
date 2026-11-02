//! Recovery authority comes from caller paths and a trusted manifest digest, never JSON paths.
use cap_fs_ext::{FollowSymlinks, MetadataExt, OpenOptionsFollowExt, OpenOptionsSyncExt};
use cap_std::fs::{Dir, OpenOptions};
use cap_tempfile::{TempDir, TempFile};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::{
    fs::File,
    io::{Read, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
};

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Entry {
    pub destination: PathBuf,
    pub stage: PathBuf,
    pub sha256: String,
}
#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub(crate) struct Journal {
    pub version: u8,
    pub entries: Vec<Entry>,
}
pub(crate) fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn descriptor_metadata(file: &File) -> Result<cap_std::fs::Metadata, String> {
    cap_std::fs::File::from_std(file.try_clone().map_err(|_| "Cannot clone file handle")?)
        .metadata()
        .map_err(|_| "Cannot read file metadata".into())
}
pub(crate) fn file_digest(file: &mut File) -> Result<String, String> {
    let metadata = descriptor_metadata(file)?;
    if !metadata.is_file() || metadata.nlink() != 1 {
        return Err("Commit file must be regular and have no hard links".into());
    }
    file.seek(SeekFrom::Start(0))
        .map_err(|_| "Cannot seek in commit file")?;
    let mut hash = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|_| "Cannot read commit file")?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hash.finalize()))
}
#[derive(PartialEq, Eq)]
enum TargetState {
    Missing,
    File {
        device: u64,
        inode: u64,
        sha256: String,
    },
}
fn target_state(dir: &Dir, name: &std::ffi::OsStr) -> Result<TargetState, String> {
    match dir.symlink_metadata(name) {
        Ok(_) => {
            let mut file = single_file(dir, name, false, false)?;
            let metadata = descriptor_metadata(&file)?;
            Ok(TargetState::File {
                device: metadata.dev(),
                inode: metadata.ino(),
                sha256: file_digest(&mut file)?,
            })
        }
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(TargetState::Missing),
        Err(_) => Err("Cannot verify target state".into()),
    }
}
struct Destination {
    path: PathBuf,
    dir: Dir,
    name: std::ffi::OsString,
    lock: File,
    initial: TargetState,
}
fn single_file(
    dir: &Dir,
    name: &std::ffi::OsStr,
    write: bool,
    create: bool,
) -> Result<File, String> {
    let mut options = OpenOptions::new();
    options
        .read(true)
        .write(write)
        .create(create)
        .follow(FollowSymlinks::No)
        .nonblock(true);
    let file = dir
        .open_with(name, &options)
        .map_err(|_| "File is missing or is not a safe regular path")?
        .into_std();
    let metadata = descriptor_metadata(&file)?;
    if !metadata.is_file() || metadata.nlink() != 1 {
        return Err("Symlinks, hard links and special files are not allowed".into());
    }
    Ok(file)
}
impl Destination {
    fn open(path: &Path) -> Result<Self, String> {
        let parent = path.parent().ok_or("Missing destination directory")?;
        let name = path
            .file_name()
            .ok_or("Missing destination name")?
            .to_os_string();
        let dir = Dir::open_ambient_dir(parent, cap_std::ambient_authority())
            .map_err(|_| "Cannot read destination directory")?;
        let lock_name = format!(
            ".{}.datasift.lock",
            name.to_str().ok_or("Destination name is not UTF-8")?
        );
        let lock = single_file(&dir, lock_name.as_ref(), true, true)?;
        lock.try_lock()
            .map_err(|_| "Output is already being written")?;
        let initial = target_state(&dir, &name)?;
        Ok(Self {
            initial,
            path: path.to_owned(),
            dir,
            name,
            lock,
        })
    }
    fn validate(&self) -> Result<(), String> {
        let parent = Dir::open_ambient_dir(
            self.path.parent().ok_or("Missing destination directory")?,
            cap_std::ambient_authority(),
        )
        .map_err(|_| "Destination directory was replaced")?;
        let original = self
            .dir
            .dir_metadata()
            .map_err(|_| "Missing directory metadata")?;
        let current = parent
            .dir_metadata()
            .map_err(|_| "Missing directory metadata")?;
        if original.dev() != current.dev() || original.ino() != current.ino() {
            return Err("Destination directory was replaced".into());
        }
        let lock_name = format!(
            ".{}.datasift.lock",
            self.name.to_str().ok_or("Invalid destination name")?
        );
        let named_lock = single_file(&self.dir, lock_name.as_ref(), false, false)?;
        let held = descriptor_metadata(&self.lock)?;
        let named = descriptor_metadata(&named_lock)?;
        if held.dev() != named.dev() || held.ino() != named.ino() {
            return Err("Output lock was replaced".into());
        }
        if target_state(&self.dir, &self.name)? != self.initial {
            return Err("Destination file changed during the transaction".into());
        }

        Ok(())
    }
    fn sync(&self) -> Result<(), String> {
        #[cfg(unix)]
        self.dir
            .try_clone()
            .map_err(|_| "Cannot clone directory")?
            .into_std_file()
            .sync_all()
            .map_err(|_| "Directory fsync failed")?;
        Ok(())
    }
}
fn valid_hash(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|b| b.is_ascii_hexdigit())
}
fn validate_manifest(journal: &Journal, targets: &[PathBuf]) -> Result<(), String> {
    if journal.version != 1
        || targets.is_empty()
        || targets.len() > 2
        || journal.entries.len() != targets.len()
    {
        return Err("Journal destinations must be fully confirmed by the caller".into());
    }
    for (i, (entry, target)) in journal.entries.iter().zip(targets).enumerate() {
        if &entry.destination != target
            || targets[..i].contains(target)
            || entry.stage.parent() != target.parent()
            || !valid_hash(&entry.sha256)
        {
            return Err("Unsafe journal or unconfirmed destination path".into());
        }
        let name = entry
            .stage
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or("Invalid stage name")?;
        let prefix = format!(
            ".{}.datasift-",
            target
                .file_name()
                .and_then(|s| s.to_str())
                .ok_or("Invalid destination name")?
        );
        let generation = name
            .strip_prefix(&prefix)
            .and_then(|s| s.strip_suffix(".tmp"))
            .ok_or("Unsafe stage path")?;
        let segments: Vec<_> = generation.split('-').collect();
        if !(2..=3).contains(&segments.len())
            || segments
                .iter()
                .any(|s| s.is_empty() || !s.bytes().all(|b| b.is_ascii_digit()))
        {
            return Err("Invalid stage identifier".into());
        }
    }
    Ok(())
}
fn journal_bytes(
    destination: &Destination,
    path: &Path,
    expected: &str,
) -> Result<Vec<u8>, String> {
    if !valid_hash(expected) {
        return Err("Trusted journal_sha256 must be a SHA-256 value".into());
    }
    let mut file = single_file(
        &destination.dir,
        path.file_name().ok_or("Missing journal name")?,
        false,
        false,
    )?;
    let mut bytes = Vec::new();
    Read::by_ref(&mut file)
        .take(16385)
        .read_to_end(&mut bytes)
        .map_err(|_| "Cannot read journal")?;
    if bytes.len() > 16384 || !digest(&bytes).eq_ignore_ascii_case(expected) {
        return Err("Journal checksum does not match journal_sha256".into());
    }
    Ok(bytes)
}
fn snapshot(source: &mut File, private: &Dir, expected: &str) -> Result<(), String> {
    let before = descriptor_metadata(source)?;
    source
        .seek(SeekFrom::Start(0))
        .map_err(|_| "Cannot seek in source file")?;
    let mut temporary = TempFile::new(private).map_err(|_| "Cannot create private snapshot")?;
    let mut hash = Sha256::new();
    let mut buffer = [0; 65536];
    loop {
        let count = source
            .read(&mut buffer)
            .map_err(|_| "Cannot read source file")?;
        if count == 0 {
            break;
        }
        hash.update(&buffer[..count]);
        temporary
            .write_all(&buffer[..count])
            .map_err(|_| "Snapshot write failed")?;
    }
    let after = descriptor_metadata(source)?;
    if before.len() != after.len()
        || before.modified().ok() != after.modified().ok()
        || before.nlink() != 1
        || after.nlink() != 1
        || format!("{:x}", hash.finalize()) != expected
    {
        return Err("Recovery file does not match journal".into());
    }
    temporary
        .as_file()
        .sync_all()
        .map_err(|_| "Snapshot fsync failed")?;
    temporary
        .replace("ready")
        .map_err(|_| "Cannot persist snapshot")
        .map(|_| ())
        .map_err(|_| "Cannot persist private snapshot".into())
}
struct Prepared {
    sources: Vec<Option<File>>,
    private: Vec<TempDir>,
}
impl Prepared {
    fn new(journal: &Journal, destinations: &[Destination]) -> Result<Self, String> {
        let mut sources = Vec::new();
        let mut private = Vec::new();
        for (entry, destination) in journal.entries.iter().zip(destinations) {
            destination.validate()?;
            let stage = entry.stage.file_name().ok_or("Missing stage name")?;
            let source = match destination.dir.symlink_metadata(stage) {
                Ok(_) => Some(single_file(&destination.dir, stage, false, false)?),
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
                    let mut completed =
                        single_file(&destination.dir, &destination.name, false, false)?;
                    if file_digest(&mut completed)? != entry.sha256 {
                        return Err("Recovery file does not match journal".into());
                    }
                    None
                }
                Err(_) => return Err("Cannot verify stage".into()),
            };
            let directory = TempDir::new_in(&destination.dir)
                .map_err(|_| "Cannot create private recovery directory")?;
            #[cfg(unix)]
            {
                use cap_std::fs::PermissionsExt;
                directory
                    .set_permissions(".", cap_std::fs::Permissions::from_mode(0o700))
                    .map_err(|_| "Cannot secure private directory")?;
            }
            if let Some(mut file) = source {
                snapshot(&mut file, &directory, &entry.sha256)?;
                sources.push(Some(file));
            } else {
                sources.push(None);
            }
            private.push(directory);
        }
        Ok(Self { sources, private })
    }
    fn install(
        self,
        path: &Path,
        expected: &str,
        destinations: &[Destination],
    ) -> Result<(), String> {
        let Self { sources, private } = self;
        journal_bytes(&destinations[0], path, expected)?;
        for ((destination, private), source) in destinations.iter().zip(&private).zip(&sources) {
            destination.validate()?;
            if source.is_some() {
                // Only a verified private copy is renamed; the external stage pathname is never used.
                private
                    .rename("ready", &destination.dir, &destination.name)
                    .map_err(|_| "Commit incomplete; journal and stages preserved")?;
                destination.sync()?;
            }
        }
        journal_bytes(&destinations[0], path, expected)?;
        destinations[0]
            .dir
            .remove_file(path.file_name().ok_or("Missing journal name")?)
            .map_err(|_| "Commit complete, journal removal failed")?;
        destinations[0].sync()
    }
}

pub(crate) struct Transaction {
    destinations: Vec<Destination>,
}
impl Transaction {
    pub fn new(targets: &[PathBuf]) -> Result<Self, String> {
        Ok(Self {
            destinations: targets
                .iter()
                .map(|p| Destination::open(p))
                .collect::<Result<Vec<_>, _>>()?,
        })
    }
    pub fn create_stage(&self, index: usize, path: &Path) -> Result<File, String> {
        let destination = &self.destinations[index];
        destination.validate()?;
        let mut options = OpenOptions::new();
        options
            .read(true)
            .write(true)
            .create_new(true)
            .follow(FollowSymlinks::No);
        #[cfg(unix)]
        {
            use cap_std::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        destination
            .dir
            .open_with(path.file_name().ok_or("Missing stage name")?, &options)
            .map(|file| file.into_std())
            .map_err(|_| "Cannot safely create stage".into())
    }
    pub fn write_journal(&self, path: &Path, bytes: &[u8]) -> Result<(), String> {
        let mut file = self.create_stage(0, path)?;
        file.write_all(bytes).map_err(|_| "Journal write failed")?;
        file.sync_all().map_err(|_| "Journal fsync failed")?;
        self.destinations[0].sync()
    }
    pub fn has_journal(&self, path: &Path) -> bool {
        self.destinations[0]
            .dir
            .symlink_metadata(path.file_name().unwrap_or_default())
            .is_ok()
    }
    pub fn cleanup(&self, journal: &Journal) {
        for (entry, destination) in journal.entries.iter().zip(&self.destinations) {
            if let Some(name) = entry.stage.file_name() {
                let _ = destination.dir.remove_file(name);
            }
        }
    }
    pub fn commit(&self, journal: &Journal, path: &Path, expected: &str) -> Result<(), String> {
        let targets: Vec<_> = self.destinations.iter().map(|d| d.path.clone()).collect();
        validate_manifest(journal, &targets)?;
        journal_bytes(&self.destinations[0], path, expected)?;
        Prepared::new(journal, &self.destinations)?.install(path, expected, &self.destinations)
    }
}
pub(crate) fn recover(targets: Vec<PathBuf>, path: &Path, expected: &str) -> Result<(), String> {
    let first = Destination::open(targets.first().ok_or("Missing output")?)?;
    let bytes = journal_bytes(&first, path, expected)?;
    let journal: Journal = serde_json::from_slice(&bytes).map_err(|_| "Invalid journal")?;
    validate_manifest(&journal, &targets)?;
    let mut destinations = vec![first];
    for target in targets.iter().skip(1) {
        destinations.push(Destination::open(target)?);
    }
    Prepared::new(&journal, &destinations)?.install(path, expected, &destinations)
}

#[cfg(test)]
#[path = "../tests/unit/recovery.rs"]
mod tests;
