//! Strict incremental transcoding: malformed byte sequences are I/O failures.
use encoding_rs::{Decoder, DecoderResult, Encoding};
use std::io::{self, Read};
pub struct StrictDecoder<R> {
    input: R,
    decoder: Decoder,
    buffer: [u8; 8192],
    start: usize,
    end: usize,
    eof: bool,
    finished: bool,
}
impl<R: Read> StrictDecoder<R> {
    pub fn new(input: R, encoding: &'static Encoding) -> Self {
        Self {
            input,
            decoder: encoding.new_decoder_with_bom_removal(),
            buffer: [0; 8192],
            start: 0,
            end: 0,
            eof: false,
            finished: false,
        }
    }
}
impl<R: Read> Read for StrictDecoder<R> {
    fn read(&mut self, out: &mut [u8]) -> io::Result<usize> {
        if out.is_empty() || self.finished {
            return Ok(0);
        }
        // A UTF-8 character needs four output bytes; csv uses larger buffers.
        if out.len() < 4 {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "Decoder requires four output bytes",
            ));
        }
        loop {
            if self.start == self.end && !self.eof {
                self.end = self.input.read(&mut self.buffer)?;
                self.start = 0;
                self.eof = self.end == 0;
            }
            let (result, read, written) = self.decoder.decode_to_utf8_without_replacement(
                &self.buffer[self.start..self.end],
                out,
                self.eof,
            );
            self.start += read;
            match result {
                DecoderResult::Malformed(_, _) => {
                    return Err(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "Invalid CSV encoding",
                    ))
                }
                DecoderResult::InputEmpty if self.eof => self.finished = true,
                _ => (),
            }
            if written > 0 || self.finished {
                return Ok(written);
            }
        }
    }
}

#[cfg(test)]
#[path = "../tests/unit/encoding.rs"]
mod tests;
