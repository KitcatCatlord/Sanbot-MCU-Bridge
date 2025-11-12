# The Plan

## Why the rewrite?

This project was originally written in Python. This was partially because I didn't completely know exactly what this project would become, and partially because I didn't think particularly far ahead. Most of the original python library was written by me, but lots of it was at least assisted by ChatGPT - it gave me a scaffold of all of the addresses and bytes, and all of the functions that went with them, from the original Android's firmware. Unfortunately, what it gave me ended up being somewhat inaccurate, such that all I could really get working properly was the arm movement (and that was after a lot of time). I also wrote it all at once, without testing each bit - silly I know, but it just felt so slow to have to constantly pull updates and reinstall everything on my Pi every time.
Rewriting this in C++ will give me a chance to rewrite this properly, such that it all works and I don't have to spend all of my time debugging. Using C++ will also allow me to run it directly on the hardware without reinstalling everything every time, and I can publish releases and such to make it very easy. It'll also run significantly better on my Raspberry Pi (or on any device for that matter), with much less overhead. Running asynchronous tasks will also be much better - for example getting the camera feed whilst getting the microphone feed, whilst sending movement commands at the same time, will be much more reliable in C++.

TLDR:
Python is slow, C++ is fast and easy. The python library was buggy and disfunctional, C++ gives me a chance to redo it properly now that I know what I'm doing.

## Rest in progress

...