# Independent session owner

`LegacySession.hs` retains the complete `Bootstrap.CrateSession` at
`ffa3d201e4ea9c08109ff00df3f4fd66b56f3ab2`. The original source SHA-256 is
`157b4d8d07986b1074cc612b89e2482783b3c80164db5f6dc74b1ece14fa7094`.

The source was checked against that established digest and passed through the
existing `private_module_view` once, changing only the module name and removing
the export restriction. The prepared fixture SHA-256 is `62eb461a5addb449b15b288c73ba3f269cefcbb634b63681d6ce237b6138d440`. All algorithm
bodies are unchanged. The runner copies and compiles this direct fixture; it
uses the same header adapter only for the current candidate under test. Normal
runs require no Git history, source-difference ledger or PR preparation.
