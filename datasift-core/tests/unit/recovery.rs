use super::*;
use crate::test_support::TestDir;
use std::fs;

struct Fixture {
    _directory: TestDir,
    target: PathBuf,
    stage: PathBuf,
    path: PathBuf,
    journal: Journal,
    hash: String,
}
impl Fixture {
    fn new() -> Self {
        let directory = TestDir::new();
        let parent = directory.path();
        let target = parent.join("matched.ndjson");
        let stage = parent.join(".matched.ndjson.datasift-1-0.tmp");
        let path = parent.join(".matched.ndjson.datasift-commit.json");
        fs::write(&target, b"old").unwrap();
        fs::write(&stage, b"new").unwrap();
        let journal = Journal {
            version: 1,
            entries: vec![Entry {
                destination: target.clone(),
                stage: stage.clone(),
                sha256: digest(b"new"),
            }],
        };
        let bytes = serde_json::to_vec(&journal).unwrap();
        fs::write(&path, &bytes).unwrap();
        Self {
            _directory: directory,
            target,
            stage,
            path,
            journal,
            hash: digest(&bytes),
        }
    }
    fn prepare(&self) -> (Vec<Destination>, Prepared) {
        let destinations = vec![Destination::open(&self.target).unwrap()];
        let prepared = Prepared::new(&self.journal, &destinations).unwrap();
        (destinations, prepared)
    }
}
#[test]
fn stage_path_replacement_after_validation_installs_only_verified_bytes() {
    let fixture = Fixture::new();
    let (destinations, prepared) = fixture.prepare();
    fs::remove_file(&fixture.stage).unwrap();
    fs::write(&fixture.stage, b"attacker").unwrap();
    prepared
        .install(&fixture.path, &fixture.hash, &destinations)
        .unwrap();
    assert_eq!(fs::read(&fixture.target).unwrap(), b"new");
    assert_eq!(fs::read(&fixture.stage).unwrap(), b"attacker");
}
#[test]
fn source_content_change_after_snapshot_cannot_change_committed_bytes() {
    let fixture = Fixture::new();
    let (destinations, prepared) = fixture.prepare();
    fs::write(&fixture.stage, b"attacker").unwrap();
    prepared
        .install(&fixture.path, &fixture.hash, &destinations)
        .unwrap();
    assert_eq!(fs::read(&fixture.target).unwrap(), b"new");
}
#[test]
fn target_replacement_between_prepare_and_install_is_refused() {
    let fixture = Fixture::new();
    let (destinations, prepared) = fixture.prepare();
    fs::remove_file(&fixture.target).unwrap();
    fs::write(&fixture.target, b"concurrent result").unwrap();
    assert!(prepared
        .install(&fixture.path, &fixture.hash, &destinations)
        .is_err());
    assert_eq!(fs::read(&fixture.target).unwrap(), b"concurrent result");
    assert!(fixture.path.exists());
}
#[test]
fn journal_change_between_prepare_and_install_is_refused() {
    let fixture = Fixture::new();
    let (destinations, prepared) = fixture.prepare();
    fs::write(&fixture.path, b"{}").unwrap();
    assert!(prepared
        .install(&fixture.path, &fixture.hash, &destinations)
        .is_err());
    assert_eq!(fs::read(&fixture.target).unwrap(), b"old");
}
#[test]
fn lock_replacement_between_prepare_and_install_is_refused() {
    let fixture = Fixture::new();
    let (destinations, prepared) = fixture.prepare();
    let lock = fixture
        .target
        .parent()
        .unwrap()
        .join(".matched.ndjson.datasift.lock");
    fs::remove_file(&lock).unwrap();
    fs::write(&lock, b"").unwrap();
    assert!(prepared
        .install(&fixture.path, &fixture.hash, &destinations)
        .is_err());
    assert_eq!(fs::read(&fixture.target).unwrap(), b"old");
}
#[test]
fn parent_path_replacement_cannot_redirect_commit() {
    let fixture = Fixture::new();
    let parent = fixture.target.parent().unwrap().join("output");
    fs::create_dir(&parent).unwrap();
    let target = parent.join("result.ndjson");
    fs::write(&target, b"old").unwrap();
    let destination = Destination::open(&target).unwrap();
    let original = parent.with_file_name("original");
    fs::rename(&parent, &original).unwrap();
    fs::create_dir(&parent).unwrap();
    fs::write(&target, b"victim").unwrap();
    assert!(destination.validate().is_err());
    assert_eq!(fs::read(&target).unwrap(), b"victim");
    assert_eq!(fs::read(original.join("result.ndjson")).unwrap(), b"old");
}
