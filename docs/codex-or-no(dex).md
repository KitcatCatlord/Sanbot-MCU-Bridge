# Codex or No(dex)?

## dev/PseudoLogic

I've used Codex to compile these. This is because there are literally thousands of .smali files in the original firmware, and I don't have the time or .smali experience to go through it and write the logic myself. Instead, I got ChatGPT to take all of the logic from it and write it as pseudologic (as I call it). This keeps it such that I'm not vibe coding, but I also don't have to go through and search for everything myself. It also means that the code will (hopefully) be efficient and functional, and I will know my way around it properly, because I'll be writing it (possibly with the help of some others).
I've also fixed the header in the pseudologic catalog because Codex added a "compiled by Codex" line at the top and I just didn't remove it.

I was initially just using a database I generated of all of the commands, and I may still use that as a lookup table, but I figured that would also be a hassle as I'd still have to search the .smali files for all of the logic for each command myself, and there's a bunch of duplicated stuff everyhwhere and files are a mess (as decompressed firmware is), and I just don't know how to navigate it. I also don't know how smali works so that wouldn't help.

## core/gui-app/main.cpp

I used Codex to help me write this Qt application, since I don't have much experience in Qt Widgets. It didn't write the whole program for me, it simply gave me high level instructions on how to do so, which I then took and used to write the application. An example would be how I asked it how to make a slider with a set range. Whilst this may seem simple, I wanted to get this GUI out quickly so I could test commands rapidly, so I didn't want to have to read through documentation or go through more general tutorials. This is just temporary for the early indev phase of this project.

I will learn Qt Widgets properly for the production build, and write a better GUI app for that.

## Misc

ChatGPT generates all of my build scripts and updates my CMakeLists.txt file.
