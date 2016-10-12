#!/usr/bin/python
# -*- coding:utf-8 -*-

import pickle
import json

C_RAPIRO_INIT = "rapiro.init"
C_RAPIRO_JSON = "rapiro.json"

def pickle2json():
    with open(C_RAPIRO_INIT, 'rb') as f:
        rapiro = pickle.load(f)
    with open(C_RAPIRO_JSON,'w') as f:
        f.write(json.dumps(rapiro))

pickle2json()

