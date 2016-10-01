#!/usr/bin/python
# -*- coding:utf-8 -*-

############################################################
# Simple demo of of the PCA9685 PWM servo/LED controller library.
# This will move channel 0 from min to max posture repeatedly.
# Author: Tony DiCola
# License: Public Domain
############################################################

############################################################
# Command control feature for servo/LED
# Author: Takashi Kojo
# License: 
############################################################

############################################################
# imports

from __future__ import division
import os
import sys
import time
import re
import pickle
import json

# Import the PCA9685 module.
import Adafruit_PCA9685

# Getch
from getch import Getch

# Choreography data
from choreo_data import ChoreoData

############################################################
# constants

# Uncomment to enable debug output.
#import logging
#logging.basicConfig(level=logging.DEBUG)

# Initialise the PCA9685 using the default address (0x40).
pwm = Adafruit_PCA9685.PCA9685()

# Alternatively specify a different address and/or bus:
#pwm = Adafruit_PCA9685.PCA9685(address=0x41, busnum=2)

# Configure min and max servo pulse lengths
servo_min = 150  # Min pulse length out of 4096
servo_max = 600  # Max pulse length out of 4096

# Rapiro status dumpfile
C_RAPIRO_INIT = "rapiro.init"

#  0: L foot pitch
#  1: L foot yaw
#  2: L hand grip
#  3: L shoulder pitch
#  4: L shoulder roll
#  5: waist yaw
#  6: head yaw
#  7: R shoulder roll
#  8: R shoulder pitch
#  9: R hand grip
# 10: R foot yaw
# 11: R foot pitch

C_PARTS_LIST = ['foot_p_l','foot_y_l','hand_l','shld_p_l','shld_r_l',
                'waist','head',
                'shld_r_r','shld_p_r','hand_r','foot_y_r','foot_p_r']
C_PARTS_TO_INDEX = {}
C_INDEX_TO_PARTS = {}
for i in range(0,len(C_PARTS_LIST)):
    C_PARTS_TO_INDEX[C_PARTS_LIST[i]] = i
    C_INDEX_TO_PARTS[i] = C_PARTS_LIST[i]

C_CHOREO_DIR = 'choreo'

############################################################
# Helper function to make setting a servo pulse width simpler.

def set_servo_pulse(channel, pulse, verbose=True):
    pulse_length = 1000000    # 1,000,000 us per second
    pulse_length //= 60       # 60 Hz
    if verbose: print('{0}us per period'.format(pulse_length))
    pulse_length //= 4096     # 12 bits of resolution
    if verbose: print('{0}us per bit'.format(pulse_length))
    pulse *= 1000
    pulse //= pulse_length
    pwm.set_pwm(channel, 0, pulse)

# abs: absolute position (pos[ch])
# rel: relative position from absolute posture (-10,.-1,+1,+10)
def unitMove(ch, pos, abs=None, rel=0,verbose=False):
    MAX_POS = 255
    if abs is None: abs = pos[ch]
    abs += rel
    if abs < 0:       abs = 0
    if abs > MAX_POS: abs = MAX_POS
    pos[ch] = int(abs)
    pwm.set_pwm(ch, 0, int(abs))
    if verbose: print('move ch:'+str(ch)+" "+str(abs))
    return abs

def smoothMove(ch, pos, to_pos, sleep=0.01, verbose=False):
    from_pos = pos[ch]
    delta = 1 if from_pos < to_pos else -1
    for p in range(from_pos+delta, to_pos+delta, delta):
        unitMove(ch, pos, p)
        time.sleep(sleep)
    if verbose: print('smooth ch:'+str(ch)+" "+str(from_pos)+"=>"+str(to_pos))
    return to_pos - from_pos

# plist: list of (next-pos, next-next-pos, ... last-pos)
def fullSwing(ch, pos, *plist, **opts):
    verbose = opts.get('verbose',None)
    cur = pos[ch]
    if verbose: print('swing ch:'+str(ch)+" "+str(cur)+"=>"+str(plist))
    for p in plist:
        smoothMove(ch, pos, p, verbose=verbose)
    return 0

def multiMove(curr, pmulti, period=0.0, verbose=False):
    unitMoveTime = 0.001 # to be adjusted
    threshold    = 5.0   # to be adjusted
    period = period / 10.0
    delta = []; lastMove = []; moveCount = []
    for d in range(0,len(curr)):
        delta.append(0.0); lastMove.append(0); moveCount.append(0)

    MAX_STEP = 100
    step = int(float(period)/(unitMoveTime*len(curr))) + 1
    if step > MAX_STEP: step = MAX_STEP

    for i in range(0, len(curr)):
        delta[i] = (pmulti[i]-curr[i])/step
        lastMove[i] = 0

    for s in range(0, step):
        moveCount = 0
        for ch in range(0, len(curr)):
            d = delta[ch]*float((s-lastMove[ch]))
            if abs(d) > threshold:
                unitMove(ch, curr, None, d, verbose=verbose)
                lastMove[ch] = s
                moveCount += 1
        if period/step - unitMoveTime*moveCount > 0.0:
                time.sleep(period/step - unitMoveTime*moveCount)
                
    return curr
    
def choreoMove(currPos, choreo, verbose=False):
    print "choreoMove:"
    for nextPos in choreo:
        print "Period: " + str(nextPos['period']) + "  Current:" + str(currPos)
        curr = multiMove(currPos, nextPos['pos'], nextPos['period'], verbose)
    print "End   :" + str(currPos)
    return curr

def printhelp(verbose=True):
    if not verbose:
        print('Type H for help')
        return
    print('Channel Settings:')
    print('  0:foot_p_l, 1:foot_y_l, 2:hand_l, 3:shld_p_l, 4:shld_r_l, 5:waist')
    print('  6:head, 7:shld_r_r, 8:shld_p_r, 9:hand_r, 10:foot_y_r, 11:foot_p_r')
    print('  12:red, 13:green, 14:blue')
    print('Commands:')
    print('  h:-10, j:-1, k:+1, l:+10, g:full swing')
    print('  m:set center, x:set max pos, n:set min pos')
    print('  c:load choreography file, i:revert to tty (use in file)')
    print('  p:simultaneous move of multiple channels, H:help, q:quit')
    print('')

############################################################
# main procedure

def mainproc(path=None,dumpfile=None):
    # Set frequency to 60hz, good for servos.
    pwm.set_pwm_freq(60)

    printhelp()
 
    if dumpfile:
        print("Loading stat: " + dumpfile)
        with open(dumpfile, 'rb') as f:
            rapiro = pickle.load(f)
    else:
        rapiro = {"servo": {"pos": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                            "max": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0],
                            "min": [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]},
                  "led": [{"r": 0,"g":0,"bit": 0}]}

    servo = rapiro["servo"]
    led   = rapiro["led"]
    pos   = servo["pos"]
    max   = servo["max"]
    min   = servo["min"]
    
    # set initial posture positions
    for ch in range(0, len(pos)):
        unitMove(ch, pos)

    # File or tty for input commands
    getch = Getch(path=path)
    
    ch = 0
    while True:
        c = getch()
        verbose = not getch.mode

        # q, ^C: exit from control loop
        if c is None or c in ('\x03','q'):
            if getch.close(): continue
            break
        
        # \r, \n: skip
        if c in ('\r','\n'): continue
        
        # 1-9: select channel 1-15
        if c in ('0','1','2','3','4','5','6','7','8','9'):
            if c != '1':
                ch = int(c)
            else:
                c2 = getch()
                if c2 in ('0','1','2','3','4','5'):
                    ch = int(c + c2)
                else:
                    ch = 1
            if verbose: print("set current channel=" + str(ch))
            continue

        # h: move-10, j: move-1, k: move+1, l: move+10
        if   c == 'h':
            unitMove(ch, pos, rel=-10, verbose=True)
        elif c == 'j':
            unitMove(ch, pos, rel=-1, verbose=True)
        elif c == 'k':
            unitMove(ch, pos, rel=1, verbose=True)
        elif c == 'l':
            unitMove(ch, pos, rel=10, verbose=True)
        # m: force all parts to center posture
        elif c == 'm':
            mid = (servo_min+servo_max)//2
            for i in range(0, len(pos)):
                unitMove(i, pos, mid)
            if verbose: print("set all channels to " + str(mid))
        # x: set current posture as maximum
        elif c == 'x':
            max[ch] = pos[ch]
            if verbose: print("set max pos=" + str(pos[ch]))
        # n: set current posture as minimum
        elif c == 'n':
            min[ch] = pos[ch]
            if verbose: print("set min pos=" + str(pos[ch]))
        # g: move cur->min->max->cur posture
        elif c == 'g':
            fullSwing(ch, pos, min[ch], max[ch], pos[ch], verbose=True)

        # c: dance with specified choreography file (nestable)
        #   c filename
        elif c == 'c':
            if verbose: sys.stdout.write('type choreography name: ')
            choreo = getch(line=True)
            if verbose: print('')
            #choreo = re.sub(r'[^-.\w]','',choreo.strip())
            #getch.push(os.path.join(C_CHOREO_DIR,choreo))
            name = choreo.strip()
            pos  = choreoMove(pos, ChoreoData[name])
            
        # p: move posture simultaneously over specified multiple channels
        #   p [-s 1000] 1:100 2:200 ... (set 'ch:pos' pairs, '=' also allowed)
        elif c == 'p':
            if verbose: sys.stdout.write('type channel settings: ')
            param = getch(line=True)
            if verbose: print('')
            param = param.strip()
            m = re.match(r'-s *(\S+) +',param)
            period = None
            if m:
                s = m.group(1)
                period = int(s) if re.match(r'\d+$',s) else 0
                param = param[m.end():]
            pmulti = map(lambda x:map(int,re.split(r'[=:]',x)),
                         re.split(r' +',param.strip()))
            multiMove(pos, pmulti, period, verbose=verbose)
            
        # i: change command control to tty (use in choreo files)
        elif c == 'i':
            getch.push()
            
        # H: print help
        elif c == 'H':
            printhelp()
        # other chars: error
        else:
            print("INVALID COMMAND:"+c)
            printhelp(verbose=False)

    with open(C_RAPIRO_INIT, "wb") as f:
        pickle.dump(rapiro, f)
 
if __name__ == "__main__":
    print('Usage: %s [ choreo ] [ dump ]' % os.path.basename(sys.argv[0]))
    mainproc(*sys.argv[1:])
