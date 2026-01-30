# History

## What is the history of this project?

This project originally started as a Python library intended to control Sanbot’s MCUs. I later decided to rewrite it in C++ for the reasons explained below. The original repository has now been archived and privated as Sanbot-MCU-Bridge-Old, and a new repository was created since the old one had become quite messy.

## Why the rewrite?

The project was originally written in Python partially because I did not fully know what it would turn into, and partially because I did not think far enough ahead at the time. Most of the original Python library was written by me, but a large portion of it was assisted by ChatGPT. It provided a scaffold of addresses, bytes, and functions extracted from the original Android firmware.

Unfortunately, a lot of this information turned out to be inaccurate. As a result, the only part I managed to get working reliably was the arm movement, and even that took a significant amount of time. On top of this, I wrote most of the library in one go without properly testing each component. In hindsight this was a mistake, but constantly pulling updates and reinstalling everything on the Raspberry Pi made iteration feel extremely slow.

Rewriting the project in C++ gives me the opportunity to rebuild it properly, with a clearer structure and incremental testing so that everything actually works as intended. Using C++ also allows the code to run directly on the hardware without needing to reinstall dependencies each time, and makes it easier to publish proper releases. Performance will also be significantly better, especially on the Raspberry Pi, with far less overhead.

Handling asynchronous tasks will be much more reliable in C++. Running the camera feed, microphone input, and movement commands at the same time is far better suited to C++ than Python for this project.

## TL;DR

The Python prototype served as a proof-of-concept, but lacked the stability for full implementation. Transitioning to C++ gives me a clean slate and a chance to use my understanding of the system's architecture for a more robust solution.
