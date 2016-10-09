#!/usr/bin/python
# -*- coding:utf-8 -*-

############################################################
# Simple demo of of the PCA9685 PWM servo/LED controller library.
# This will move channel 0 from min to max position repeatedly.
# Author: Tony DiCola
# License: Public Domain
############################################################

############################################################
# Getch extention for file input
# Author: Nobuyuki Saji
# License: 
############################################################

############################################################
# imports

import sys

############################################################
# constants

C_MAX_DEPTH = 30000

############################################################
# class definitions

class Getch:
    def __init__(self, path=None):
        try:
            self.tty = _GetchWindows()
        except ImportError:
            self.tty = _GetchUnix()
        self.stack = []
        self.files = [path]
        self.mode = path
        self.impl = _GetchFile(path) if path else self.tty

    # 'line' reads characters until CR/LF comes and returns line string
    def __call__(self,line=False,prompt=''):
        if not line: return self.impl()

        if prompt: sys.stdout.write(prompt)
        buf = []
        c = self.impl()
        while c not in ('\r','\n'):
            if c in ('\b','\x7f'): buf.pop()
            else: buf.append(c)
            if not self.mode: sys.stdout.write(c)
            c = self.impl()
        if prompt: sys.stdout.write('\n')
        return ''.join(buf)

    # Push nested input context (tty or file)
    def push(self, path=None):
        #if path and path in self.files:
        #    raise Exception("Duplicate nested file: "+path)
        if len(self.stack) > C_MAX_DEPTH:
            raise Exception("Too many nested files: "+path)

        self.stack.append(self.impl)
        self.files.append(path)
        self.mode = path
        self.impl = _GetchFile(path) if path else self.tty

    # Pop nested input context (tty or file) if possible
    def close(self):
        if len(self.stack) > 0:
            self.impl = self.stack.pop()
            self.files.pop()
            self.mode = self.files[-1]
            return True
        return False

class _GetchUnix:
    def __init__(self):
        import tty, sys

    def __call__(self):
        import sys, tty, termios
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

class _GetchWindows:
    def __init__(self):
        import msvcrt

    def __call__(self):
        import msvcrt
        return msvcrt.getch()

class _GetchFile:
    def __init__(self, path):
        with open(path, 'r') as f:
            self.clist = sum([list(x) for x in f],[])

    def __call__(self):
        if len(self.clist)==0: return None
        return self.clist.pop(0)

############################################################
# quick test

if __name__ == "__main__":
    import sys
    getch = Getch(sys.argv[1]) if len(sys.argv)>=2 else Getch()
    print("Verbose: "+str(not getch.mode))
    while True:
        c = getch()
        if c is None or c=='q': break
        print(c)
