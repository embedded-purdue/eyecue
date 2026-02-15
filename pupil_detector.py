import cv2
import numpy as np


#Configuration

class DetectionConfig:
    """Configurable parameters for pupil detection"""
    # Contour filtering, removes noise
    MIN_CONTOUR_AREA = 1000
    MAX_ASPECT_RATIO = 3
    
    # Thresholding, limits detection to a square around the darkest point (avoids eyebrows, lashes, etc)
    THRESHOLDS = [5, 15, 25]
    MASK_SIZE = 250
    
    # Morphology
    DILATION_KERNEL_SIZE = (5, 5)
    DILATION_ITERATIONS = 2
    
    # ROI (relative to frame)
    ROI_X1 = 0.2
    ROI_Y1 = 0.3
    ROI_X2 = 0.8
    ROI_Y2 = 0.8
    
    # CLAHE contrast enhancement, used for bad or uneven lighting conditions
    CLAHE_CLIP_LIMIT = 2.0
    CLAHE_TILE_SIZE = (8, 8)


#Image Prep

def crop_to_aspect_ratio(image, width=640, height=480):
    """Crop and resize image to target aspect ratio"""
    h, w = image.shape[:2]
    desired_ratio = width / height
    current_ratio = w / h

    if current_ratio > desired_ratio:
        new_w = int(desired_ratio * h)
        offset = (w - new_w) // 2
        image = image[:, offset:offset + new_w]
    else:
        new_h = int(w / desired_ratio)
        offset = (h - new_h) // 2
        image = image[offset:offset + new_h, :]

    return cv2.resize(image, (width, height))


#Darkest Area Search

def get_darkest_area(gray):
    """Find darkest point in image using efficient min search"""
    # Blur to reduce noise and avoid single dark pixels
    blurred = cv2.GaussianBlur(gray, (15, 15), 0)
    
    # Find minimum value and location efficiently
    min_val, _, min_loc, _ = cv2.minMaxLoc(blurred)
    
    return min_loc  # Returns (x, y) tuple

#Threshold

def apply_binary_threshold(gray, darkest_value, offset):
    """Apply binary threshold based on darkest point"""
    thresh_val = darkest_value + offset
    _, thresh = cv2.threshold(gray, thresh_val, 255, cv2.THRESH_BINARY_INV)
    return thresh


def mask_square(image, center, size):
    """Create square mask around center point"""
    x, y = center
    half = size // 2
    mask = np.zeros_like(image)

    x1 = max(0, x - half)
    y1 = max(0, y - half)
    x2 = min(image.shape[1], x + half)
    y2 = min(image.shape[0], y + half)

    mask[y1:y2, x1:x2] = 255
    return cv2.bitwise_and(image, mask)


#Contour Filter

def filter_largest_valid_contour(contours, min_area=None, max_ratio=None):
    """Filter contours by area and aspect ratio, return largest valid one"""
    if min_area is None:
        min_area = DetectionConfig.MIN_CONTOUR_AREA
    if max_ratio is None:
        max_ratio = DetectionConfig.MAX_ASPECT_RATIO
    
    best = None
    best_area = 0

    for c in contours:
        area = cv2.contourArea(c)
        if area < min_area:
            continue

        x, y, w, h = cv2.boundingRect(c)
        ratio = max(w/h, h/w) if h > 0 else float('inf')

        if ratio > max_ratio:
            continue

        if area > best_area:
            best_area = area
            best = c

    return best


#Ellipse

def ellipse_goodness(binary, contour):
    """Calculate how well a contour fits an ellipse (score 0-1)"""
    if len(contour) < 5:
        return 0

    ellipse = cv2.fitEllipse(contour)

    # Create ellipse mask
    mask = np.zeros_like(binary)
    cv2.ellipse(mask, ellipse, 255, -1)

    ellipse_area = np.sum(mask == 255)
    covered = np.sum((binary == 255) & (mask == 255))

    if ellipse_area == 0:
        return 0

    fill_ratio = covered / ellipse_area

    # Calculate circularity (penalize elongated ellipses)
    axes = ellipse[1]
    if axes[1] == 0:
        return 0
    circularity = min(axes[0]/axes[1], axes[1]/axes[0])

    # Combined score: how well it fills the ellipse * how circular it is
    return fill_ratio * circularity


#Main detector

def detect_pupil_contour(frame, debug=False):
    """
    Detect pupil using contour analysis
    
    Args:
        frame: Input BGR image
        debug: If True, show intermediate processing steps
    
    Returns:
        pupil_center: (x, y) tuple or None
        roi_center: (x, y) center of ROI
        bbox: (x, y, w, h) bounding box or None
    """
    frame = crop_to_aspect_ratio(frame)
    h, w = frame.shape[:2]

    # Define ROI
    roi_x1 = int(w * DetectionConfig.ROI_X1)
    roi_y1 = int(h * DetectionConfig.ROI_Y1)
    roi_x2 = int(w * DetectionConfig.ROI_X2)
    roi_y2 = int(h * DetectionConfig.ROI_Y2)

    roi = frame[roi_y1:roi_y2, roi_x1:roi_x2]
    roi_center = ((roi_x1 + roi_x2)//2, (roi_y1 + roi_y2)//2)

    # Convert to grayscale
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    
    # Apply CLAHE for better contrast in varying lighting
    clahe = cv2.createCLAHE(clipLimit=DetectionConfig.CLAHE_CLIP_LIMIT, 
                           tileGridSize=DetectionConfig.CLAHE_TILE_SIZE)
    gray = clahe.apply(gray)
    
    # Find darkest point (pupil center candidate)
    darkest_point = get_darkest_area(gray)

    if darkest_point is None:
        return None, roi_center, None

    darkest_value = gray[darkest_point[1], darkest_point[0]]

    # Try multiple thresholds to find best pupil contour
    best_score = 0
    best_contour = None
    best_binary = None
    
    kernel = np.ones(DetectionConfig.DILATION_KERNEL_SIZE, np.uint8)

    for t in DetectionConfig.THRESHOLDS:
        binary = apply_binary_threshold(gray, darkest_value, t)
        binary = mask_square(binary, darkest_point, DetectionConfig.MASK_SIZE)
        binary = cv2.dilate(binary, kernel, iterations=DetectionConfig.DILATION_ITERATIONS)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contour = filter_largest_valid_contour(contours)

        if contour is None:
            continue

        score = ellipse_goodness(binary, contour)

        if score > best_score:
            best_score = score
            best_contour = contour
            best_binary = binary.copy()

    # Debug visualization
    if debug and best_binary is not None:
        cv2.imshow("1. Gray ROI (CLAHE)", gray)
        cv2.imshow("2. Best Binary", best_binary)
        if best_contour is not None:
            debug_frame = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            cv2.drawContours(debug_frame, [best_contour], -1, (0, 255, 0), 2)
            cv2.circle(debug_frame, darkest_point, 5, (0, 0, 255), -1)
            cv2.imshow("3. Best Contour", debug_frame)

    if best_contour is None or len(best_contour) < 5:
        return None, roi_center, None

    # Fit ellipse to contour
    ellipse = cv2.fitEllipse(best_contour)
    (cx, cy), axes, angle = ellipse

    pupil_center = (int(cx + roi_x1), int(cy + roi_y1))
    
    x, y, bw, bh = cv2.boundingRect(best_contour)
    bbox = (x + roi_x1, y + roi_y1, bw, bh)

    return pupil_center, roi_center, bbox