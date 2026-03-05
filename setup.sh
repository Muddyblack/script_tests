#!/bin/bash
# Add current user to input group for ghost typist
sudo usermod -aG input $(whoami)