#!/usr/bin/python

#program ini mengenali wajah dari input image yang dihasilkan dari fungsi capture via camera
#camera yang dipakai adalah jenis modular
#Akan ada perbedaan di fungsi stream (untuk mempermudah saja mungkin mas-mas mau memakai webcam)
#Mencari dan mengenali wajah dengan tiga kemungkinan rotasi
#sudut -10 derajat, 0 derajat original, dan +10 derajat
#angka +-10 bisa dirubah


#mengimport bahan2 yang diperlukan
import numpy, cv2, sys, os, math, time, picamera
import paho.mqtt.publish as publish

from skimage.measure import structural_similarity as ssim
from difflib import SequenceMatcher
from PIL import Image
from skimage import data, img_as_float
import matplotlib.pyplot as plt
from picamera.array import PiRGBArray

#start time
start = time.time()

#push data ke server
def pushData(data):
    publish.single("face/rec/test", data, hostname="test.mosquitto.org")
    return;
    
def elapseTime(end):
    global start
    elapsed = end - start
    print "Total waktu: "+ '%s' %(elapsed) 
    return;

#ukuran scaling, 1 berarti diperkecil 1 atau normal
size = 1
#ukuran skala untuk tampilan di dekstop
size_im = 854, 640

#set Threshold
#nilai threshold bisa diganti,,,sumber asli adalah 500
#semakin besar nilai kemungkinan miss detection semakin rendah
#akan tetapi meningkatkan peluang salah pengenalan
thr = 600

#sudut rotasi
#di code ini memakai tiga orientasi berbeda untuk proses deteksi dan recognation
#memakai fix sudut -10 derajat dan +10 derajat, -10 derajat adalah arah putaran CW
angle1 = -10
angle2 = 10

#membuat list array kosong untuk database nama wajah terdeteksi
person = []

#nilai dari 180/pi, dengan pi=3.14
x = 57.2957795131


"""
cos1 = math.cos(angle1/x)
cos2 = math.cos(angle2/x)
"""

#mendefine fungsi rotasi titik terhadap titik, angle/sudut dalam derajat
#perlu untuk menyesuaikan letak posisi kotak muka terdeteksi dengan hasil rotasi frame image
#keluaran adalah titik hasil rotasi
def rotate(origin, point, angle):
    ox, oy = origin
    px, py = point

    qx = int(math.floor(ox + math.cos(angle/x) * (px - ox) - math.sin(angle) * (py - oy)))
    qy = int(math.floor(oy + math.sin(angle) * (px - ox) + math.cos(angle) * (py - oy)))
    return qx, qy

#meload fungsi haar cascade karangan om jones dan memberi perintah create/access directory 
face_cascade = cv2.CascadeClassifier('haarcascade_frontalface_default.xml')
fn_haar = 'haarcascade_frontalface_default.xml'
fn_dir = 'att_faces'

# Part 1: Create fisherRecognizer
print('Training...')

#inisiasi perintah ngeload image
# Create a list of images and a list of corresponding names
(images, lables, names_ori, id) = ([], [], {}, 0)
(images, lables, names_rot1, id) = ([], [], {}, 0)
(images, lables, names_rot2, id) = ([], [], {}, 0)

#Memuat file2 gambar di database terhadap database buffer tersendiri di program 
# Get the folders containing the training data
for (subdirs, dirs, files) in os.walk(fn_dir):

    # Loop through each folder named after the subject in the photos
    # dibuat tiga jenis fungsi for karena memakai 3 orientasi sehingga tidak saling tumpang tindih
    for subdir in dirs:
        names_ori[id] = subdir
        names_rot1[id] = subdir
        names_rot2[id] = subdir
        subjectpath = os.path.join(fn_dir, subdir) #menjoinkan home directory program dengan
                                                   #subdir berisi database gambar training

        # Loop through each photo in the folder / memuat setiap gambar satu persatu
        for filename in os.listdir(subjectpath):

            # Skip non-image formates
            f_name, f_extension = os.path.splitext(filename)
            if(f_extension.lower() not in
                    ['.png','.jpg','.jpeg','.gif','.pgm']):
                print("Skipping "+filename+", wrong file type")
                continue
            path = subjectpath + '/' + filename
            lable = id

            # Add to training data
            images.append(cv2.imread(path, 0))
            lables.append(int(lable))
        id += 1

#set ukuran lebar dan tinggi gambar, karena proses recognasi wajib memakai ukuran yang sama
#terutama fungsi structural similarity
(im_width, im_height) = (112, 92) 

# Create a Numpy array from the two lists above / bikin array
(images, lables) = [numpy.array(lis) for lis in [images, lables]]

# OpenCV trains a model from the images
# NOTE FOR OpenCV2: remove '.face'
#memanggil fungsi Fisher recognition dan mewakilkannya dengan perintah 'model'
model = cv2.createFisherFaceRecognizer()
model.train(images, lables)

# Part 2: Use fisherRecognizer on camera stream (kagak dipakai pada sistem image detection)
haar_cascade = cv2.CascadeClassifier(fn_haar)


#Mengaktifkan camera dan menyiapkan input

# initialize the camera and grab a reference to the raw camera capture
camera = picamera.PiCamera()
camera.resolution = (2592, 1944)
camera.framerate = 20
rawCapture = PiRGBArray(camera, size=camera.resolution)

#code ini bisa dihapus..dipakai karena posisi kamera default saat pengusunan adalah terbalik
#camera.vflip = True

#Menghapus input proses sebelumnya
os.remove('Test.png')

print "Capturing Image, Please Wait"

# allow the camera to warmup
time.sleep(1)

camera.capture('Test.png')

print "Image Captured"
time.sleep(0.5)

print "Processing"

# input gambar berada di folder yang sama dengan program disimpan
img = cv2.imread('Test.png')
img_pre = img.copy()

#mengambil informasi ukuran gambar yang dimuat
rows, cols = img.shape[:2]

#mengeset matrik rotasi, dibutuhkan untuk merotasi gambar input yang dimuat
rotation_matrix1 = cv2.getRotationMatrix2D((cols/2, rows/2), angle1, 1)
rotation_matrix1_inv = cv2.getRotationMatrix2D((cols/2, rows/2), (-angle1), 1)
rotation_matrix2 = cv2.getRotationMatrix2D((cols/2, rows/2), angle2, 1)
rotation_matrix2_inv = cv2.getRotationMatrix2D((cols/2, rows/2), (-angle2), 1)

#fungsi haar hanya bekerja mendeteksi pada skala grayscale, jadi dibuat gray image
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

print "Proses Pertama"
#mendeteksi letak wajah pada file gray hasil konversi sebelumnya, dengan rejection level 1.3
faces = face_cascade.detectMultiScale(gray, 1.3, 5)

if len(faces)==0:
    print "Undetected Faces on Original Position"
    output_ori = img_pre.copy()
    output_ori_show = cv2.resize(output_ori, size_im)
    end = time.time()
    elapseTime(end)

else :
    print "Found Faces on Original Position"
    #set Region of Interest (ROI), bagian yang menarik hati
    for (x,y,w,h) in faces:
        for i in range(len(faces)): #len(faces) mewakili banyak wajah terdeteksi
            face_i = faces[i]
           
            # Coordinates of face after scaling back by `size` (skaling ukuran kotak)
            (x, y, w, h) = [v * size for v in face_i]
            face = gray[y:y + h, x:x + w]
            face_resize = cv2.resize(face, (im_height, im_width))

            # Try to recognize the face
            prediction = model.predict(face_resize)
            print "Prediction value is "+ '%s' %(prediction[1])
            #prediction[1] berisi nilai penentu yang akan mencocokan input dengan database wajah
            #prediction[0] adalah nama di database

            for n in range(20):
                if prediction[1] >= thr : #memberi nilai threshold thr, menghindari miss deteksi meski kemungkinan menambah pFa
                    # Write the name of recognized face
                    print names_ori[prediction[0]]
                    pushData(names_ori[prediction[0]])
                    break
                    
                    one = names_ori[prediction] #
                    person.append(one) #menambahkan isi list array person dengan nama terdeteksi sebelumnya
                    len_ori = len(person)
                                        
                else:
                    cv2.putText(img, 'Unknown Person', (x-10, y-10), cv2.FONT_HERSHEY_PLAIN,3,(0, 0, 255), 2)
                    one = "Unknown Person"
                    person.append(one)
                    len_ori = len(person)
                    print one
                    break
                    
            end = time.time()
            elapseTime(end)
                
            roi_gray = gray[y:y+h, x:x+w]
            roi_color = img[y:y+h, x:x+w]

            output_ori = img_pre.copy() #menduplikat full img inputan, sebagai dasar input rotasi 1

            #menyiapkan pembolongan
            for (x,y,w,h) in faces:
                output_ori[y:y+h, x:x+w] = [255] #255 adalah index warna putih

#output_ori_show adalah skaling dari output_ori agar memudahkan penampilan saja..begitu saja dengan variable _show yang lainnya
#hal ini menjaga agar proses tetap dilakukan pada resolusi tertinggi yang dimungkinkan kamera
output_ori_show = cv2.resize(output_ori, size_im)


#Rotasi pertama
#memnyiapkan input
#merotasi dulu
output_ori_roted = cv2.warpAffine(output_ori, rotation_matrix1, (cols, rows))
output_ori_roted_pre = output_ori_roted.copy()
    
#konvert ke gray
gray_output_ori_roted = cv2.cvtColor(output_ori_roted, cv2.COLOR_BGR2GRAY)
        
#sama seperti kisah2 di atas, hanya lain judul, rot1 untuk rotasi pertama, rot2 rotasi2
faces_rot1 = face_cascade.detectMultiScale(gray_output_ori_roted, 1.3, 5)

print "Proses Kedua"

if len(faces_rot1)==0:
    print "Undetected Faces on Rotation 1"
    output_rot1 = output_ori_roted.copy()
    output_rot1_show = cv2.resize(output_rot1, size_im)
    end = time.time()
    elapseTime(end)
    
else:
    print "Found Faces on Rotation 1"
    for (x1,y1,w,h) in faces_rot1:
        roi_gray_rot1 = gray_output_ori_roted[y1:y1+h, x1:x1+w]
        roi_color_rot1 = output_ori_roted[y1:y1+h, x1:x1+w]

        for i in range(len(faces_rot1)):
            face_i = faces_rot1[i]

            # Coordinates of face after scaling back by `size`
            (x1, y1, w, h) = [v * size for v in face_i]
            face_rot1 = gray_output_ori_roted[y1:y1 + h, x1:x1 + w]
            face_resize_rot1 = cv2.resize(face_rot1, (im_height, im_width))
                    
            # Try to recognize the face
            prediction = model.predict(face_resize_rot1)
            print "Prediction value is "+ '%s' %(prediction[1])

            for m in range(20):
                if prediction[1] >= thr :
                    # Write the name of recognized face
                    print names_rot1[prediction[0]]
                    pushData(names_rot1[prediction[0]])
                    two = names_rot1[prediction[0]]
                    person.append(two)
                    len_rot1 = len(person)
                    break
                            
                else:
                    two = "Unknown Person"
                    person.append(two)
                    len_rot1 = len(person)
                    print two
                    break
                    
            end = time.time()
            elapseTime(end)
                      
            roi_gray_rot1 = gray_output_ori_roted[y1:y1+h, x1:x1+w]
            roi_color_rot1 = output_ori_roted[y1:y1+h, x1:x1+w]

            output_rot1 = output_ori_roted_pre.copy()

            for (x1,y1,w,h) in faces_rot1:
                output_rot1[y1:y1+h, x1:x1+w] = [255]

output_rot1_show = cv2.resize(output_rot1, size_im)

#Rotasi kedua
#memnyiapkan input
#merotasi dulu
rows1, cols1 = output_rot1.shape[:2]
#mengembalikan orientasi dari hasil output pertama
output_rot1_norm = cv2.warpAffine(output_rot1, rotation_matrix1_inv, (cols1, rows1))
#menambah rotasi untuk persiapan input rotasi 2
input_rot2 = cv2.warpAffine(output_rot1_norm, rotation_matrix2, (cols1, rows1))
input_rot2_show = cv2.resize(input_rot2, size_im)
input_rot2_pre = input_rot2.copy()
    
#konvert ke gray
gray_input_rot2 = cv2.cvtColor(input_rot2, cv2.COLOR_BGR2GRAY)
        
#sama seperti kisah2 di atas, hanya lain judul, rot1 untuk rotasi pertama, rot2 rotasi2
faces_rot2 = face_cascade.detectMultiScale(gray_input_rot2, 1.3, 5)

print "Proses Ketiga"

if len(faces_rot2)==0:
    print "Undetected Faces on Rotation 2"
    output_rot2 = input_rot2_pre
    output_rot2_show = cv2.resize(output_rot2, size_im)
    end = time.time()
    elapseTime(end)

else:
    print "Found Faces on Rotation 2"
    for (x2,y2,w,h) in faces_rot2:
        roi_gray_rot2 = gray_output_ori_roted[y2:y2+h, x2:x2+w]
        roi_color_rot2 = output_ori_roted[y2:y2+h, x2:x2+w]

        for i in range(len(faces_rot2)):
            face_i = faces_rot2[i]

            # Coordinates of face after scaling back by `size`
            (x2, y2, w, h) = [v * size for v in face_i]
            face_rot2 = gray_output_ori_roted[y2:y2 + h, x2:x2 + w]
            face_resize_rot2 = cv2.resize(face_rot2, (im_height, im_width))
                    
            # Try to recognize the face
            prediction = model.predict(face_resize_rot2)
            print "Prediction Value:"+ '%s' %(prediction[1])

            for m in range(20):
                if prediction[1] >= thr :
                    # Write the name of recognized face
                    print names_rot2[prediction[0]]
                    pushData(names_rot2[prediction[0]])
                    three = names_rot2[prediction[0]]
                    person.append(three)
                    len_rot2 = len(person)
                    break
                            
                else:
                    three = "Unknown Person"
                    person.append(three)
                    len_rot2 = len(person)
                    print three
                    break
            
            end = time.time()
            elapseTime(end)
                      
            roi_gray_rot2 = gray_output_ori_roted[y2:y2+h, x2:x2+w]
            roi_color_rot2 = output_ori_roted[y2:y2+h, x2:x2+w]

            output_rot2 = output_ori_roted_pre.copy()

            for (x2,y2,w,h) in faces_rot2:
                output_rot2[y2:y2+h, x2:x2+w] = [255]       

            output_rot2_show = cv2.resize(output_rot2, size_im)

cv2.waitKey(0)
cv2.destroyAllWindows()
