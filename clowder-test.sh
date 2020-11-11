#!/bin/bash

pytest  --junitxml=results.xml
python post_results.py
