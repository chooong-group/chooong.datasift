use super::StrictDecoder;
use encoding_rs::{UTF_16LE, UTF_8, WINDOWS_1252};
use std::io::{self, Cursor, Read};

struct Chunked<'a> {
    bytes: &'a [u8],
    size: usize,
}

impl Read for Chunked<'_> {
    fn read(&mut self, out: &mut [u8]) -> io::Result<usize> {
        let count = self.size.min(out.len()).min(self.bytes.len());
        out[..count].copy_from_slice(&self.bytes[..count]);
        self.bytes = &self.bytes[count..];
        Ok(count)
    }
}

fn decode(mut decoder: impl Read) -> io::Result<String> {
    let mut bytes = Vec::new();
    let mut buffer = [0; 7];
    loop {
        let count = decoder.read(&mut buffer)?;
        if count == 0 {
            return Ok(String::from_utf8(bytes).unwrap());
        }
        bytes.extend_from_slice(&buffer[..count]);
    }
}

#[test]
fn multibyte_characters_and_boms_survive_input_boundaries() {
    for (encoding, bytes, expected) in [
        (
            UTF_8,
            b"\xef\xbb\xbfGr\xc3\xbc\xc3\x9fe \xf0\x9f\x8c\x8d".as_slice(),
            "Grüße 🌍",
        ),
        (
            UTF_16LE,
            b"\xff\xfeA\0\xac\x20\x3c\xd8\x0d\xdf".as_slice(),
            "A€🌍",
        ),
        (WINDOWS_1252, b"Gr\xfc\xdfe \x80".as_slice(), "Grüße €"),
    ] {
        for size in [1, 2, 3, 8192] {
            let mut decoder = StrictDecoder::new(Chunked { bytes, size }, encoding);
            let output = decode(&mut decoder).unwrap();
            assert_eq!(
                output,
                expected,
                "{} with chunk size {size}",
                encoding.name()
            );
            assert_eq!(decoder.read(&mut [0; 4]).unwrap(), 0);
        }
    }
}

#[test]
fn malformed_and_truncated_sequences_are_errors_instead_of_replacement_text() {
    for (encoding, bytes) in [
        (UTF_8, b"a\xff".as_slice()),
        (UTF_8, b"\xe2\x82".as_slice()),
        (UTF_16LE, b"\xff\xfeA".as_slice()),
        (UTF_16LE, b"\xff\xfe\x00\xd8".as_slice()),
    ] {
        let mut decoder = StrictDecoder::new(Chunked { bytes, size: 1 }, encoding);
        let error = decode(&mut decoder).unwrap_err();
        assert_eq!(
            error.kind(),
            io::ErrorKind::InvalidData,
            "{}: {bytes:?}",
            encoding.name()
        );
    }
}

#[test]
fn output_buffer_validation_does_not_consume_input() {
    let mut decoder = StrictDecoder::new(Cursor::new("€"), UTF_8);
    assert_eq!(decoder.read(&mut []).unwrap(), 0);
    assert_eq!(
        decoder.read(&mut [0; 3]).unwrap_err().kind(),
        io::ErrorKind::InvalidInput
    );
    let output = decode(&mut decoder).unwrap();
    assert_eq!(output, "€");
}

#[test]
fn input_io_failure_is_preserved() {
    struct FailedInput;
    impl Read for FailedInput {
        fn read(&mut self, _: &mut [u8]) -> io::Result<usize> {
            Err(io::ErrorKind::PermissionDenied.into())
        }
    }
    let error = StrictDecoder::new(FailedInput, UTF_8)
        .read(&mut [0; 8])
        .unwrap_err();
    assert_eq!(error.kind(), io::ErrorKind::PermissionDenied);
}
