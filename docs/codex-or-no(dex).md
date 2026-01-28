# Codex or No(dex)?

## dev/PseudoLogic

I've used Codex to compile these. This is because there are literally thousands of .smali files in the original firmware, and I don't have the time or .smali experience to go through it and write the logic myself. Instead, I got ChatGPT to take all of the logic from it and write it as pseudologic (as I call it). This keeps it such that I'm not vibe coding, but I also don't have to go through and search for everything myself. It also means that the code will (hopefully) be efficient and functional, and I will know my way around it properly, because I'll be writing it (possibly with the help of some others).
I've also fixed the header in the pseudologic catalog because Codex added a "compiled by Codex" line at the top and I just didn't remove it.

I was initially just using a database I generated of all of the commands, and I may still use that as a lookup table, but I figured that would also be a hassle as I'd still have to search the .smali files for all of the logic for each command myself, and there's a bunch of duplicated stuff everyhwhere and files are a mess (as decompressed firmware is), and I just don't know how to navigate it. I also don't know how smali works so that wouldn't help.
