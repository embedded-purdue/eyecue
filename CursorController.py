# -*- coding: utf-8 -*-
"""
Created on Thu Sep 25 17:43:39 2025

@author:    Luca DalCanto, Purdue University
            on behalf of the Eyecue team of ES@P

The purpose of this class is to take the 9-dot calibration information,
position of the eye at any given time, and head angles at any given 
time (from gyro) to calculate the correct position of the mouse on the
screen.

How to use:
    
    - import this file ("import CursorController") or something idk
    
    - create an instance of this class after calibration:
            
        "controller = CursorController(...parameters here...)"
            
        parameters of instantitaion:
            - leftAngle: nine-dot left calibration horizontal angle in degrees
            - rightAngle: nine-dot right calibration horizontal angle in degrees
            - topAngle: nine-dot top calibration vertical angle in degrees
            - bottomAngle: nine-dot bottom calibration vertical angle in degrees
            - gyroH: initial horizontal angle of gyro
            - gyroV: intial vertial angle of gyro
            - frameRate: intended number of updates per second
                
    - every frame, call the update function:
        
        "controller.update_target(...parameters here...)"
        
        parameters of update_target:
            - angleH: current horizontal eye angle in degrees
            - angleV: current vertical eye angle in degrees
            - gyroH: current horizontal gyro angle
            - gyroV: current vertical gyro angle
    
Areas for improvement:
    - calculates correct mapping with screen distance and screen size using the 
    horizontal angles only -> mapping for vertical angles may be imperfect.
    - 


"""
import pyautogui
import math
import numpy as np


class CursorController:

    # Constructor method
    def __init__(self, leftAngle, rightAngle, topAngle, bottomAngle, gyroH, gyroV, frameRate):
        self.frameRate = frameRate
        self.screenWidth, self.screenHeight = pyautogui.size()
        
        leftAngle *= math.pi / 180
        rightAngle *= math.pi / 180
        topAngle *= math.pi/180
        bottomAngle *= math.pi/180
        
        self.screenDistance = self.screenWidth / (2 * math.tan(abs(leftAngle - rightAngle)/2))
        self.gyroCenter = [gyroH, gyroV]
        self.eyeCenter = [(leftAngle + rightAngle) / 2, (topAngle + bottomAngle) / 2]
        
        print(self.eyeCenter[1])
        
    
    # takes angle of vision (angle H - horizontal, angleV - vertical) in degrees
    # takes angle of head (gyroH, gyroV) in degrees
    def update_target(self, angleH, angleV, gyroH, gyroV):
        
        # convert horizontal and vertical rotations to radians
        angleH *= math.pi / 180
        angleV *= -math.pi / 180
        
        # account for initial calibration
        angleH -= self.eyeCenter[0]
        angleV += self.eyeCenter[1]
        
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
        scaleFactor = self.screenDistance / unitVector[1]        # cos theta sub
        
        # calculate position in coordinates
        x = (unitVector[0] * scaleFactor) + (self.screenWidth / 2)
        y = (unitVector[2] * scaleFactor) + (self.screenHeight/2)
        
        pyautogui.moveTo(x, y, duration=1.0/self.frameRate)
        


# control = CursorController(0, 56.8, 16.3, -16.3, 0, 0)
# control.update_target(0, -17.3, 0, 0)