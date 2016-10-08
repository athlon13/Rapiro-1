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

# initial Choreography data

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
                'shld_r_r','shld_p_r','hand_r','foot_y_r','foot_p_r',
                'ch 12','ch 13','ch 14','ch 15']
C_PARTS_TO_INDEX = {}
C_INDEX_TO_PARTS = {}
for i in range(0,len(C_PARTS_LIST)):
    C_PARTS_TO_INDEX[C_PARTS_LIST[i]] = i
    C_INDEX_TO_PARTS[i] = C_PARTS_LIST[i]

C_CHOREO_DIR = 'choreo'

C_MINIMUM_SLEEP = 0.001

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

DUTY_0 = 100    # duty for 0 degree
DUTY_180 = 620  # duty for 180 degree

def unitMove(servo, ch, abs=None, rel=0, verbose=False):
    pos = servo['pos']
    if abs is None: abs = pos[ch]
    abs += rel
    pos[ch] = abs
    pwm.set_pwm(ch, 0, int(DUTY_0 + abs*DUTY_180/180))
    if verbose: print('move ch:'+str(ch)+" "+str(abs))
    return abs

def smoothMove(servo, ch, pos, to_pos, sleep=0.01, verbose=False):
    pos = servo['pos']
    from_pos = pos[ch]
    delta = 1 if from_pos < to_pos else -1
    for p in range(from_pos+delta, to_pos+delta, delta):
        unitMove(servo, ch, pos, p)
        time.sleep(sleep)
    if verbose: print('smooth ch:'+str(ch)+" "+str(from_pos)+"=>"+str(to_pos))
    return to_pos - from_pos

# plist: list of (next-pos, next-next-pos, ... last-pos)
def Swing(servo, ch, pos, *plist, **opts):
    pos = servo['pos']
    verbose = opts.get('verbose',None)
    cur = pos[ch]
    if verbose: print('swing ch:'+str(ch)+" "+str(cur)+"=>"+str(plist))
    time = 1000
    for p in plist:
        #smoothMove(servo, ch, pos, p, verbose=verbose)
        multiMove(servo, [[ch, p]], time)
    return 0

def fullSwing(servo, ch, time, verbose=False):
    cur = servo['pos'][ch]
    max = servo['max'][ch]
    min = servo['min'][ch]
    if verbose: print('swing ch:'+str(ch)+" "+str(cur)+"=>"+str(min)+"=>"+str(max)+"=>"+str(cur))   
    multiMove(servo, [[ch, min]], time)
    multiMove(servo, [[ch, max]], time)
    multiMove(servo, [[ch, cur]], time)

def multiMove(servo, pmulti, period, sleep=0.01, verbose=False):
    pos = servo['pos']
    limit_max = servo['max']
    limit_min = servo['min']

    if not period:
        for ch,p in pmulti:
            if limit_max[ch] < p: p = limit_max[ch]
            if limit_min[ch] > p: p = limit_min[ch]   
            adj =  int((limit_max[ch] + limit_min[ch])/2) - 90         
            unitMove(servo, ch, p+adj, verbose=verbose)
        time.sleep(sleep)
    else:
        basestep = int(period/(sleep*1000))
        chstep = 1 #servo_max
        totalstep = 0
        for xp in pmulti:
            # xp: [ch, to_pos] + [cur_pos, delta, round_error]
            ch = xp[0]
            # cur_pos: xp[2]
            xp.append(pos[ch])
            print str(xp)
            if limit_max[ch] < xp[2]:
                xp[2] = limit_max[ch]
            elif limit_min[ch] > xp[2]:
                xp[2] = limit_min[ch]           
            # delta: xp[3]
            d = xp[1] - xp[2]
            xp.append(d)
            chstep = max(abs(d), chstep)
            totalstep += abs(d)
            # round error: xp[4]
            xp.append(0.001*(1 if xp[3]>=0 else -1))
        # ここでステップ数を確定する。現在は稼働chの平均動作回数としている
        # 全chの最大移動幅とベース回数(上記)の小さい方とするなどの変更が可能
        #step = min(step, chstep)
        step = int(totalstep/len(pmulti))

        # 与えられた達成目標時間(-s period指定)に対して上記で定めたステップ数を回す
        # １ステップ毎に処理時間を実測し、残り時間で残りステップをこなせるように
        # 毎回sleep値を補正
        period /= 1000.0
        print('period=%.3f sec, step=%d'%(period,step))
        #verbose = True
        for s in range(step-1,-1,-1):
            # 最新の１ステップの処理時間を計測しておく
            utimer = time.time()
            for xp in pmulti:
                xp[2] += xp[3] / step
                unitMove(servo, xp[0], int(round(xp[2]+xp[4])), verbose=verbose)
            curr = time.time() - utimer
            # 予定されたステップ数を終了したらループから抜ける
            if s==0:
                #print('Execution time error: %.3f sec'%period)
                break

            period -= curr
            if period > 0:
                # 残り時間が正の場合、残り時間と残りステップ数からsleep可能な時間を計算
                unit = period / s
                #print('step=%d, period=%.3f, curr=%.3f, unit=%.3f'%(s,period,curr,unit))
                if unit > curr:
                    sleep = unit - curr
                    period -= sleep
                    time.sleep(sleep)
                else:
                    # 可能sleep時間が負になってしまう場合は、最小sleepして処理を継続
                    time.sleep(C_MINIMUM_SLEEP)
            else:
                # 残り時間が負(達成目標時間を超過)の場合は、最小sleepして処理を継続
                time.sleep(C_MINIMUM_SLEEP)

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
    print('  p:simultaneous move of mult-channels, t[se]:timer, H:help, q:quit')
    print('')

############################################################
# main procedure

def mainproc(path=None,dumpfile=None):
    # Set frequency to 60hz, good for servos.
    pwm.set_pwm_freq(60)

    printhelp()
 
    MAX_CH = 16
    SERVO_MIDDLE = 90
    SERVO_MAX    = 180
    SERVO_MIN    = 0
        
    if dumpfile:
        print("Loading stat: " + dumpfile)
        with open(dumpfile, 'rb') as fin:
            rapiro = pickle.load(fin)
    else:
        rapiro = {"servo": {"pos": [SERVO_MIDDLE] * MAX_CH,
                            "max": [SERVO_MAX] * MAX_CH,
                            "min": [SERVO_MIN] * MAX_CH,
                            "parts": range(0, MAX_CH)},
                  "led": [{"r": 0,"g":0,"bit": 0}]}

    servo = rapiro["servo"]
    led   = rapiro["led"]
    pos   = servo["pos"]
    max   = servo["max"]
    min   = servo["min"]
    parts = servo["parts"]
    
    # set initial posture positions
    for ch in range(0, len(pos)):
        unitMove(servo, ch, pos[ch])

    # File or tty for input commands
    if path == '-':
        getch = Getch(path=None)
    else:    
        getch = Getch(path=path)
    
    ch = 0
    while True:
        c = getch()
        verbose = not getch.mode
        print "Input:" + str(c)
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
            if verbose: print("set current channel=" + str(parts[ch]) + ": " + C_PARTS_LIST[parts[ch]])
            continue
        
        # measure elapsed time and print in seconds between 'ts' and 'te'
        if c == 't':
            c2 = getch()
            if c2 == 's':
                if verbose: sys.stdout.write('ts')
                title = getch(line=True).strip()
                if verbose: print(title)
                timer = time.time()
            elif c2 == 'e':
                print('Elapsed time: %s %.3f sec'%(title,time.time()-timer))
            else:
                pass
            continue

        # h: move-10, j: move-1, k: move+1, l: move+10
        if   c == 'h':
            unitMove(servo, ch, rel=-10, verbose=True)
        elif c == 'j':
            unitMove(servo, ch, rel=-1, verbose=True)
        elif c == 'k':
            unitMove(servo, ch, rel=1, verbose=True)
        elif c == 'l':
            unitMove(servo, ch, rel=10, verbose=True)
        # m: force all parts to center posture
        elif c == 'm':
            mid = SERVO_MIDDLE  # 90 degree
            for i in range(0, len(pos)):
                unitMove(servo, i, mid)
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
            time = 1000
            fullSwing(servo, ch, time, verbose=True)

        # c: dance with specified choreography file (nestable)
        #   c filename
        elif c == 'c':
            if verbose: sys.stdout.write('type choreography file: ')
            choreo = getch(line=True)
            j = re.match(r'-j *(\S+) +',choreo)
            if verbose: print('')
            choreo = re.sub(r'[^-.\w]','',choreo.strip())
            getch.push(os.path.join(C_CHOREO_DIR,choreo))

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
                print str(period) + str(param)
            pmulti = map(lambda x:map(int,re.split(r'[=:]',x)),
                         re.split(r' +',param.strip()))
            multiMove(servo, pmulti, period, verbose=verbose)
        elif c == 'a': # Asign logical channel and parts name
            parts[ch] = (parts[ch] + 1) % len(pos)
            if verbose: print("Part name: " + C_PARTS_LIST[parts[ch]])          

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
