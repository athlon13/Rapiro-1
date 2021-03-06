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
# Author: Nobuyuki Saji, Takashi Kojo
# License:
############################################################

############################################################
# imports

from __future__ import division
import os
import sys
import time
from datetime import datetime
import re
import json
import ssl
import threading

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

# Rapiro configuration
C_RAPIRO_CONF = "config.json"

# Rapiro status dumpfile
C_RAPIRO_INIT = "rapiro.init"
C_RAPIRO_JSON = "rapiro.json"

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

C_CHOREO_DIR = 'choreo'

C_MINIMUM_SLEEP = 0.001
C_MAX_CH          = 16
############################################################
# External Control Feature

def getnow():
    return datetime.utcnow().isoformat()[:-3]+'Z'

from scsender import SCsender

ext_control = None
def init_ext_control(host, session):
    global ext_control
    if ext_control is None:
         ext_control = SCsender(host=host, session=session)

def get_ext_control(verbose=False):
    global ext_control
    ext_control.add('dummy',getnow(),'X',0)
    out = ''
    try:
        ret = ext_control.post(retry=1,wait=1,keep_on_error=False)
        out = str(ret.read())
        if verbose: print('RECV: '+out)
    except:
        if verbose: print('ERROR')
    return out

############################################################
# Helper function to make setting a servo pulse width simpler.

def make_choreo_path(file):
    return os.path.join(C_CHOREO_DIR,file)

def initproc(verbose=False):
    input = open(C_RAPIRO_CONF,'r')
    conf = json.loads(input.read())
    input.close()
    if verbose:
        for k,v in conf.items(): print('CONF: '+k+'='+str(v))
    return conf

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

class unitMoveThread(threading.Thread):
    def __init__(self, servo):
        threading.Thread.__init__(self)
        self.servo = servo

    def run(self):
        save_pos   = [0] * C_MAX_CH
        save_bias  = [0] * C_MAX_CH
        save_scale = [0] * C_MAX_CH
        servo = self.servo
        self._running = True
        while self._running:
            for ch in range(C_MAX_CH):
                pos = servo['pos'][ch]
                bias = servo['bias'][ch]
                scale = servo['scale'][ch]
                if (save_pos[ch] != pos) or \
                   (save_bias[ch] != bias) or \
                   (save_scale[ch] != scale):
                    save_pos[ch] = unitMove_body(servo, ch, pos)
            time.sleep(C_MINIMUM_SLEEP)

    def shutdown(self):
        self._running = False

def unitMove_body(servo, ch, abs=None, rel=0, verbose=False):
    pos   = servo['pos']
    bias  = servo['bias']
    scale = servo['scale']
    phys  = servo['phys']
    if abs is None: abs = pos[ch]
    abs += rel
    pos[ch] = abs
    pwm.set_pwm(phys[ch], 0, int(DUTY_0 + (abs+bias[ch])*scale[ch]*DUTY_180/180))
    if verbose: print('move ch:'+str(ch)+" "+str(abs))
    return abs

def unitMove(servo, ch, abs=None, rel=0, verbose=False):
    pos = servo['pos']
    if abs is None: abs = pos[ch]
    abs += rel
    pos[ch] = abs
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

class multiMoveThread(threading.Thread):
    def __init__(self, servo, pmulti, period, sleep, verbose):
        threading.Thread.__init__(self)
        self.servo = servo
        self.pmulti = pmulti
        self.period = period
        self.sleep = sleep
        self. verbose = verbose
    def run(self):
        multiMove(self.servo, self.pmulti, self.period, self.sleep)
        self._running = False

def multiMove_nb(servo, pmulti, period, sleep=0.01, verbose=False):
    mvThread = multiMoveThread(servo, pmulti, period, sleep, verbose)
    mvThread.start()

def multiMove(servo, pmulti, period=0.0, sleep=0.01, verbose=False):
    pos = servo['pos']
    limit_max = servo['max']
    limit_min = servo['min']

    if sleep  == None: sleep = 0.0
    if period == None: period = 0.0

    basestep = int(period/(sleep*1000))
    chstep = 1 #servo_max
    totalstep = 0

    for xp in pmulti:
        # xp: [ch, to_pos] + [cur_pos, delta, round_error]
        ch = xp[0]
        # cur_pos: xp[2]
        xp.append(pos[ch])
        if verbose: print(str(xp))
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

    step = int(totalstep/len(pmulti))
    period /= 1000.0
    if verbose:
        print('period=%.3f sec, step=%d'%(period,step))

    for s in range(step-1,-1,-1):
        for xp in pmulti:
            xp[2] += xp[3] / step
            unitMove(servo, xp[0], int(round(xp[2]+xp[4])), verbose=verbose)
        if s==0:
            break
        time.sleep(period/step)

def printhelp(verbose=True):
    if not verbose:
        print('Type H for help')
        return
    print('Channel Settings:')
    print('  0:foot_p_l, 1:foot_y_l, 2:hand_l, 3:shld_p_l, 4:shld_r_l, 5:waist')
    print('  6:head, 7:shld_r_r, 8:shld_p_r, 9:hand_r, 10:foot_y_r, 11:foot_p_r')
    print('  12:red, 13:green, 14:blue')
    print('Commands:')
    print('  h:-10, j:-1, k:+1, l:+10, +, -: bias, *, /: scale, g:full swing')
    print('  m:set center, x:set max pos, n:set min pos')
    print('  c:load choreography file, i:revert to tty (use in file)')
    print('  p:simultaneous move of multi-channels, s:get external control')
    print('  ts,te:timer start and end, H:help, q:quit')

    print('Choreography files:')
    (i, m) = (0, 8)
    for fn in sorted(os.listdir(C_CHOREO_DIR)):
        if i==0: sys.stdout.write('  ')
        sys.stdout.write(fn)
        sys.stdout.write('\n' if i==m-1 else ' ')
        i = (i+1) % m
    if i!=0: print('')
    print('')

############################################################
# main procedure

def mainproc(script=None,dumpfile=None):
    # Initialization of Rapiro Controller
    conf = initproc()
    init_ext_control(conf['endpoint'], conf['session'])

    # Set frequency to 60hz, good for servos.
    pwm.set_pwm_freq(60)

    SERVO_MIDDLE = 90
    SERVO_MAX    = 180
    SERVO_MIN    = 0

    if dumpfile and os.path.exists(dumpfile):
        print("Loading stat: " + dumpfile)
        with open(C_RAPIRO_JSON,'r') as f:
            rapiro = json.loads(f.read())
    else:
        rapiro = {"servo": {"pos": [SERVO_MIDDLE] * C_MAX_CH,
                            "max": [SERVO_MAX] * C_MAX_CH,
                            "min": [SERVO_MIN] * C_MAX_CH,
                            "bias": [0]   * C_MAX_CH,
                            "scale":[1.0] * C_MAX_CH,
                            "name": ['']  * C_MAX_CH,
                            "phys": range(0, C_MAX_CH)}}

    servo = rapiro["servo"]
    name  = servo["name"]
    pos   = servo["pos"]
    max   = servo["max"]
    min   = servo["min"]
    bias  = servo["bias"]
    scale = servo["scale"]
    phys  = servo["phys"]

    C_PARTS_TO_INDEX = {}
    C_INDEX_TO_PARTS = {}
    for i in range(0,len(name)):
        C_PARTS_TO_INDEX[name[i]] = i
        C_INDEX_TO_PARTS[i] = name[i]

    unitMove_th = unitMoveThread(servo)
    unitMove_th.start()

    # set initial posture positions
    for ch in range(0, len(pos)):
        unitMove(servo, ch, pos[ch])

    # File or tty for input commands
    if script in (None,'-'):
        getch = Getch(path=None)
    else:
        getch = Getch(path=make_choreo_path(script))

    # initial posture
    getch.push(make_choreo_path('upright'))

    verboseloop = False
    ch = 0
    while True:
        c = getch()
        verbose = verboseloop or not getch.mode
        #print("Input:" + str(c))
        # ^C: force exit from control loop
        # q: close current input stream
        if c == '\x03':
            break
        if c is None or c == 'q':
            verboseloop = False
            if getch.close(): continue
            break

        # \r, \n: skip
        if c in ('\r','\n'):
            continue

        # #: comment out
        if c == '#':
            getch(line=True)
            if verbose: print('')
            continue

        # v: set verbose flag for script
        if c == 'v':
            v = getch(line=True,prompt=verbose and 'type 1 or 0: ').strip()
            verboseloop = bool(int(v))
            continue

        # y: just print message on console
        if c == 'y':
            print(getch(line=True,
                        prompt=verbose and 'type message: ').strip())
            continue

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
            if verbose: print("set current channel=" + str(ch) + ": " + name[ch])
            continue

        # measure elapsed time and print in seconds between 'ts' and 'te'
        if c == 't':
            c2 = getch()
            if c2 == 's':
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
            swtime = 1000
            fullSwing(servo, ch, swtime, verbose=True)
        elif c == '+':
            bias[ch] += 1
            print("bias=" + str(bias[ch]))
            unitMove(servo, ch)
        elif c == '-':
            bias[ch] -= 1
            print("bias=" + str(bias[ch]))
            unitMove(servo, ch)
        elif c == '*':
            scale[ch] *= 1.01
            print("scale=" + str(scale[ch]))
            unitMove(servo, ch)
        elif c == '/':
            scale[ch] *= 0.99
            print("scale=" + str(scale[ch]))
            unitMove(servo, ch)
        # c: dance with specified choreography file (nestable)
        #   c filename [repeat]
        elif c == 'c':
            choreo = getch(line=True,
                           prompt=verbose and 'type choreo file: ').strip()
            m = re.match(r'([-.\w]+)( +\d+)?',choreo)
            if not m:
                print('usage: c choreo_file [repeat]')
                continue
            repeat = int(m.group(2) or '1')
            choreo = m.group(1)
            filename = make_choreo_path(choreo)
            print('file='+filename+' repeat='+str(repeat))
            if not os.path.exists(filename):
                print('choreo file %s not exists'%choreo)
                continue
            for x in range(0,repeat): getch.push(filename)

        # p: move posture simultaneously over specified multiple channels
        #   p [-n] [-s 1000] 1:100 2:200 ...
        #   (set 'ch:pos' pairs, '=' also allowed)
        elif c == 'p':
            param = getch(line=True,
                          prompt=verbose and 'type channel settings: ').strip()
            m = re.match(r'( *-n +)? *-s *(\S+) +',param)
            nonBlock = False
            period = None
            if m:
                nonBlock = bool(m.group(1))
                s = m.group(2)
                period = int(s) if re.match(r'\d+$',s) else 0
                param = param[m.end():]
                print('p'+(' -n' if nonBlock else '')+
                      ' -s '+str(period)+' '+str(param))
            pmulti = map(lambda x:map(int,re.split(r'[=:]',x)),
                         re.split(r' +',param.strip()))
            if nonBlock:
                multiMove_nb(servo, pmulti, period, verbose=verbose)
            else:
                multiMove(servo, pmulti, period, verbose=verbose)

        # get external control
        # 1,1,feedback:c=COMMAND;g=GROUP;s=SID;t=TIMESTAMP;v=VALUE[LOWER:UPPER]
        # (1) VALUE should be [10, 50], and be mapped to 1,2,3,4,5
        # (2) select and execute choreo file 'choreo1',... respectively
        elif c == 's':
            ext = get_ext_control()
            if not re.search(r'feedback:',ext): continue

            _m = re.search(r';v=([.\d]+)',ext)
            if not _m: continue

            distance = float(_m.group(1))
            print('DISTANCE: '+str(distance))
            # extract 1, 2, ... as choreo-ID
            choreoid = int(distance/10)
            if choreoid < 1 or 4 < choreoid: continue
            getch.push(make_choreo_path('choreo'+str(choreoid)))

        # i: change command control to tty (use in choreo files)
        elif c == 'i':
            getch.push()

        # w: wait (in milliseconds)
        elif c == 'w':
            param = getch(line=True,
                          prompt=verbose and 'type milliseconds: ').strip()
            wait = int(param) if re.match(r'\d+$',param) else 1000
            time.sleep(wait/1000)
        # H: print help
        elif c == 'H':
            printhelp()
        # other chars: error
        else:
            print("INVALID COMMAND:"+c)
            printhelp(verbose=False)

    unitMove_th.shutdown()    # end of unitMove Thread
    with open(dumpfile or C_RAPIRO_JSON,'w') as f:
        f.write(json.dumps(rapiro))

if __name__ == "__main__":
    print('Type H for print help\n')
    if len(sys.argv) <= 3:
        mainproc(*sys.argv[1:])
    else:
        print('Usage: %s [ choreo | - ] [ dumpfile ]'%os.path.basename(sys.argv[0]))
