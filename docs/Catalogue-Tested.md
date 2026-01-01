# Tested working catalog from control-catalog.cpp

This is a list of commands which I have tested and know are functional. This is all done by main.cpp parser reference (i.e what you type in the command line)

## Tested

### Locomotion

Head:
- head-relative
    - up
    - down
    - left
    - right
    - left-up
    - left-down
    - right-up
    - right-down
- head-centre

Wheels:
- wheel-relative
    - forward

### Not working

Head:
- head-relative
    - vertical-reset
    - horizontal-reset
    - centre-reset

Wheels:
- wheel-distance
    - right - goes left

## Untested

Head:
- head-relative
    - stop
