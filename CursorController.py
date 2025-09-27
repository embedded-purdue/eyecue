# -*- coding: utf-8 -*-
"""
Created on Thu Sep 25 17:43:39 2025

@author: Luca DalCanto

The purpose of this class is to take the 9-dot calibration information,
position of the eye at any given time, and head angles at any given 
time (from gyro) to calculate the correct position of the mouse on the
screen.

Assumptions:
    - face is centered compared to screen left-to-right and camera left-to-right
    (this assumption only holds up using a webcam, not glasses likely)
    


"""
import pyautogui
import math
import numpy as np


class CursorController:

    # Constructor method
    def __init__(self, leftAngle, rightAngle, topAngle, bottomAngle, gyroH, gyroV):
        self.frameRate = 2
        self.screenWidth, self.screenHeight = pyautogui.size()
        
        self.screenDistance = self.screenWidth / (2 * math.tan(abs(leftAngle - rightAngle)/2))
        top = self.screenDistance * math.tan(topAngle)
        bottom = self.screenDistance * math.tan(bottomAngle)
        self.vertDisplacement = top - bottom
        self.gyroCenter = [gyroH, gyroV]
        
    
    # takes angle of vision (angle H - horizontal, angleV - vertical) in degrees
    # takes angle of head (gyroH, gyroV) in degrees
    def update_target(self, angleH, angleV, gyroH, gyroV):
        
        # convert horizontal and vertical rotations to radians
        angleH *= math.pi / 180
        angleV *= math.pi / 180
        
        # account for head rotation
        angleH += (gyroH - self.gyroCenter[0]) * math.pi / 180
        angleV += (gyroV - self.gyroCenter[1]) * math.pi / 180
        
        # gaze vector
        unitVector = np.array([
            np.sin(angleH) * np.cos(angleV),   # x-component
            np.cos(angleH) * np.cos(angleV),   # y-component
            np.sin(angleV)                     # z-component
        ])
        
        # scale unit vector according to distance from screen
        scaleFactor = self.screenDistance
        
        # calculate position in coordinates
        x = (unitVector[0] * scaleFactor) + (self.screenWidth / 2)
        y = (unitVector[2] * scaleFactor) + self.vertDisplacement + (self.screenHeight/2)
        
        pyautogui.moveTo(self.targetScreenPosition[0], self.targetScreenPosition[1], duration=1.0/self.frameRate)
        