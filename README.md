# 🎓 FACEGUARD – AI-Based Smart Attendance System

FACEGUARD is an AI-powered attendance system designed to eliminate proxy attendance and enhance classroom security. It combines face recognition, liveness detection, and session-based verification to ensure only genuine students are marked present.


## 📌 Features

- 🔐 **User Authentication**
  - Separate login for Teachers and Students
  - Secure session handling

- 🧑‍🏫 **Session Management**
  - Teachers generate unique session codes
  - Time-limited session validity

- 🤖 **Face Recognition**
  - Identifies students using facial features
  - Uses stored face encodings for verification

- 👁️ **Liveness Detection (Anti-Spoofing)**
  - Detects real human presence (blink / head movement)
  - Prevents fake attendance using photos or videos

- 📍 **Location / Network Validation**
  - Ensures student is in the classroom environment
  - Can verify WiFi/IP range

- 📊 **Attendance System**
  - Marks attendance with timestamp
  - Prevents duplicate entries

- 📄 **Report Generation**
  - Export attendance as Excel / PDF
  - Easy for teachers to maintain records


## 🛠️ Tech Stack

### 💻 Frontend
- HTML
- CSS
- JavaScript (or React)

### ⚙️ Backend
- Python (Flask / FastAPI)

### 🗄️ Database
- SQLite (initial)
- MySQL (optional upgrade)

### 🤖 AI / ML Libraries
- OpenCV
- face_recognition
- dlib

## 🚀 How It Works

1. Teacher logs in and creates a session  
2. System generates a unique session code  
3. Student logs in and enters session code  
4. Camera opens for face verification  
5. System performs:
   - Face recognition  
   - Liveness detection  
   - Location check  
6. If all checks pass → Attendance marked ✅  

## 🔍 Modules Explained

### 🔑 Authentication Module
Handles login/signup for teachers and students.

### 📡 Session Module
Generates and validates session codes.

### 🧠 Face Recognition Module
Matches live face with stored encoding.

### 👀 Liveness Detection Module
Ensures the user is physically present.

### 📊 Attendance Module
Stores and manages attendance records.


## 🔥 Future Enhancements

- 📱 Mobile App Integration  
- 📈 Attendance Analytics Dashboard  
- ☁️ Cloud Database (Firebase / AWS)  
- 🧑‍💼 Admin Panel  
- 🎯 Multi-Class Support  


## ⚠️ Limitations

- Requires good lighting for accurate detection  
- Webcam quality affects performance  
- Basic liveness detection can be improved with deep learning  


## 👨‍💻 Contributors

- Giridhari Mandal 
- Jagannath Dalei
- Biswaranjan Biswal
- Biswas Benya
- Kiran Jyoti Sahoo

## 📜 License

This project is developed for academic purposes.  
You may modify and use it with proper credit.

## 🙌 Acknowledgement

- OpenCV Community  
- face_recognition Library  
- dlib Contributors  


## 📬 Contact

For queries or collaboration:

- Email: jagannathd935@gmail.com  
- GitHub: https://github.com/jagannathd935