
# Simple demo of of the PCA9685 PWM servo/LED controller library.
# This will move channel 0 from min to max position repeatedly.
# Author: Tony DiCola
# License: Public Domain
#from __future__ import division
import time
#import pickle
import sys
import RPi.GPIO as GPIO

class _Getch:
    def __init__(self):
        try:
            self.impl = _GetchWindows()
        except ImportError:
            self.impl = _GetchUnix()

    def __call__(self): return self.impl()

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

min_duty = 1.0
max_duty = 15.0
max_degree = 180.0

#ch_pin = [8, 3, 5, 7, 10, 11,13,15,18, 19,21,23,26,32,29,31,33,35,37,40]
ch_pin = [8, 3, 5, 7, 10, 11,13,15,18, 19,21,23]
pwm  = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

def init_servo():
	GPIO.setmode(GPIO.BOARD)
	GPIO.setwarnings(False)

	ch_num = len(ch_pin)
	print str(ch_num) + " Channels"

	for i in range(0, ch_num):
        	print "Channel:" + str(ch_pin[i])
        	GPIO.setup(ch_pin[i], GPIO.OUT)
        	pwm[i] = GPIO.PWM(ch_pin[i], 50.0)
        	pwm[i].start(ch_pin[i])
        	pwm[i].ChangeDutyCycle((max_duty+min_duty)/2.0)

def set_servo(ch, degree):
	duty = (max_duty - min_duty)/max_degree*degree
	p = pwm[ch]
	p.ChangeDutyCycle(duty)

def smoothMove(ch, from_pos, to_pos):
	if from_pos < to_pos:
		delta = 1
	else:
		delta = -1

	p = from_pos
        while True:
                set_servo(ch, 0, p)
                if p == to_pos:
                         break
                else:
                        p += delta
                time.sleep(0.01)

def fullSwing(ch, min, max):
        curr = rapiro["servo"]["pos"][ch]
	print str(ch) + "," +  str(curr)
	smoothMove(ch, curr, min)
	print str(ch) + "," +  str(min)
	smoothMove(ch, min, max)
	print str(ch) + "," +  str(max)
	smoothMove(ch, max, curr)	
	print str(ch) + "," +  str(curr)


print('Moving , <- . || / -> _, 0 - 11 for channel, "q" to quit...')
getch = _Getch()

pos    = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
max    = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
min    = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
led    = [ { "r": 0, "g": 0, "b": 0}] 
servo  = {"pos": pos, "max":max, "min":min }
rapiro = {"servo":servo, "led":led}

init_servo()
if len(sys.argv) == 2:
	print "Loading stat: " + sys.argv[1] 
	with open(sys.argv[1], 'rb') as f:
		rapiro = pickle.load(f) 

ch = 0
while True:
	time.sleep(1.0)
	c = "0"
	#c = getch()
	if   c == ',':
		rapiro["servo"]["pos"][ch] -= 10
	elif c == '.':
                rapiro["servo"]["pos"][ch] -= 1
	elif c == '/':
                rapiro["servo"]["pos"][ch] += 1
	elif c == '_':
                rapiro["servo"]["pos"][ch] +=10
	elif c == 'm':
		for i in range(0, len(ch_pin)):
			set_servo(i, 90.0)
			rapiro["servo"]["pos"][i] = 90.0
	elif c == 'x':
		rapiro["servo"]["max"][ch] = rapiro["servo"]["pos"][ch]
	elif c == 'n':
		rapiro["servo"]["min"][ch] = rapiro["servo"]["pos"][ch]
	elif c == 'g':
		fullSwing(ch, rapiro["servo"]["min"][ch], rapiro["servo"]["max"][ch])
	elif c == 'q':
		break
	elif int(c) in range(0, 10):
		if int(c) != 1:
			ch = int(c)
		else:
			c2 = getch()
			if c2 in ["0","1","2","3","4","5","6","7","8","9"]:
				ch = int(c + c2)
			else:
			    ch = 1
	set_servo(ch, rapiro["servo"]["pos"][ch])
	print str(ch) + ", " + str(rapiro["servo"]["pos"][ch])

with open("rapiro.init", "wb") as f:
	pickle.dump(rapiro, f)
