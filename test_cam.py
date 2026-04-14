import cv2

cap = cv2.VideoCapture(0)

cap.set(3, 1280)  # width
cap.set(4, 720)   # height

print("Attempting to open webcam in a new window...")
print("Press ESC while focused on the video window to close it.")

while True:
    ret, frame = cap.read()
    if not ret:
        print("Error: Could not read frame from webcam.")
        break
    
    cv2.imshow("Camera", frame)

    # 27 is the ASCII code for the ESC key
    if cv2.waitKey(1) == 27:
        print("ESC pressed. Exiting...")
        break

cap.release()
cv2.destroyAllWindows()
