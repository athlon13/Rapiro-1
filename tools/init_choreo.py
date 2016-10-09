#!/usr/bin/python
# -*- coding:utf-8 -*-

from __future__ import division
import os
import sys
import time
import re
import pickle
import json
import codecs

from choreo_data import ChoreoData

#print json.dumps(ChoreoData)
c = []
for c in ChoreoData:
    print str(c)
    fout = codecs.open('./choreo/' + str(c), 'w')
    for posture in ChoreoData[c]:
        pos = posture['pos']
        line_pos = 'p -s ' + str(posture['period']*100) + ' '
        for i in range(0, len(pos)):
            line_pos += str(i) + ':' + str(pos[i]) + " "
        print line_pos
        fout.write(line_pos+'\n')
    fout.close()
    
#print json.dumps(ChoreoData, sort_keys=True,indent=4, separators=(',', ': '))
