# -*- coding: utf-8 -*-
"""
Created on Thu Sep 25 17:43:39 2025

@author: Luca DalCanto

The purpose of this class is to take the 9-dot calibration information,
position of the eye at any given time, and head angles at any given 
time (from gyro) to calculate the correct position of the mouse on the
screen.


"""
import pyautogui
import math


class CursorController:
    # Class attributes
    frameRate = 30
    tlVect, trVect, blVect, brVect = [], [], [], []
    targetScreenPosition = []
    screenWidth, screenHeight = 0, 0

    # Constructor method
    def __init__(self, topLeftVector, topRightVector, bottomLeftVector, bottomRightVector):
        self.tlVect = topLeftVector
        self.trVect = topRightVector
        self.blVect = bottomLeftVector
        self.brVect = bottomRightVector 
        self.screenWidth, self.screenHeight = pyautogui.size()
        
    def update_target(self, visionVector, headRotationHoriz):
        
        # convert horizontal and vertical rotations to radians
        
        # account for horizontal head rotation     
        rawVector = visionVector
        visionVector[0] = ((rawVector[0] * math.cos(headRotationHoriz)) - 
                           (rawVector[2] * math.sin(headRotationHoriz)))
        visionVector[2] = ((rawVector[0] * math.sin(headRotationHoriz)) + 
                           (rawVector[2] * math.cos(headRotationHoriz)))
        
        # find target on screen
        x_top = (visionVector[0] - self.tlVect[0]) / (self.trVect[0] - self.tlVect[0])
        x_bottom = (visionVector[0] - self.blVect[0]) / (self.brVect[0] - self.blVect[0])
        y_left = (visionVector[0] - self.tlVect[0]) / (self.blVect[0] - self.tlVect[0])
        y_right = (visionVector[0] - self.trVect[0]) / (self.brVect[0] - self.trVect[0])
        self.targetScreenPosition = [self.screenWidth * (x_top + x_bottom) / 2, 
                                self.screenHeight * (y_left + y_right) / 2]
        

    # Regular methods
    def update_mouse(self):
        pyautogui.moveTo(self.targetScreenPosition[0], self.targetScreenPosition[1], duration=1.0/self.frameRate)