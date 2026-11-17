# Bulk byte-array CRC

`byteArrayCRC32 :: ByteArray -> Int -> Int -> IO Int` returns CRC32/ISO-HDLC of
the array at action execution, treating the interval `[start, start + count)`
as zero without changing the array. The positive result occupies 32 bits of
`Int`. `(0, 0)` computes the ordinary CRC, including zero for an empty array.

The action forces the array, then checks `0 <= start <= length`, then checks
`0 <= count <= length - start`. Invalid ranges fail with `invalid CRC zero
range`; constructing the IO action forces none of these arguments. Addition
cannot overflow after those checks. This is corruption detection, not a content
identity or authentication mechanism; SHA-256 content addresses are unchanged.

The primitive was introduced at code 134 with the `/14` builtin interface and
`mlf-primitive-135-v10` ABI. Its code remains 134 in the later
[field-framing ABI](string-fields.md). The binary wire checksum and file format are unchanged.
Only the encoder's private completed-plan path uses the bulk operation; public
prefix-length checksum and raw bit writers retain their existing behavior.
