{-# LANGUAGE OverloadedStrings #-}
module Main where
import LiteralProvider (Key(..), key)
main = print (case (key,42 :: Int) of { ("a",0) -> 0; ("b",x) -> x; _ -> 99 })
