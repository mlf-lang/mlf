# Independent session owner

`LegacySession.hs` retains the complete `Bootstrap.CrateSession` at
`e123603d00f6f64e20e4d771836e49ddd808320f`. The original source SHA-256 is
`18abedc7f96452392ed3401f1ae607233ec13e2a5ba24bd1c0cba344820c382f`.

The source was checked against that established digest and passed through the
existing `private_module_view` once, changing only the module name and removing
the export restriction. The prepared fixture SHA-256 is `93f8d5f686c05a8e2b56ef279c53a0ef0351af6f1ac7207746ee04623358fc66`. All algorithm
bodies are unchanged. The runner copies and compiles this direct fixture; it
uses the same header adapter only for the current candidate under test. Normal
runs require no Git history, source-difference ledger or PR preparation.
