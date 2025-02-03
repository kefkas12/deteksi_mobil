import cv2
import streamlit as st
from ultralytics import YOLO
from tracker import Tracker
import tempfile
import mysql.connector
from datetime import datetime
import time
import numpy as np

# Muat model YOLO
model = YOLO('best.pt')

# Daftar kelas yang dapat dideteksi oleh model YOLO
class_list = model.names

# Inisialisasi objek pelacak
tracker = Tracker()

# st.markdown(
#     """
#     <style>
#     /* Memusatkan label number_input */
#     div[data-testid="stNumberInput"] > label {
#         display: block;
#         text-align: center;
#         width: 100%;
#     }
#     /* Memusatkan teks di dalam input */
#     div[data-testid="stNumberInput"] input {
#         text-align: center;
#     }

#     </style>
#     """,
#     unsafe_allow_html=True
# )

# Fungsi untuk menyimpan data deteksi ke database MySQL
def save_to_mysql(timestamp, car_count, bus_count, truck_count, total_count, traffic_density):
    # connection = mysql.connector.connect(
    #     host='localhost',
    #     user='root',
    #     password='',
    #     database='vehicle_detection'
    # )
    connection = mysql.connector.connect(
        host='srv1151.hstgr.io',
        port='3306',
        user='u860014930_vehicle',
        password='D3m0n12!',
        database='u860014930_vehicle'
    )
    cursor = connection.cursor()
    insert_query = """
    INSERT INTO detection_history (timestamp, car_count, bus_count, truck_count, total_count, traffic_density)
    VALUES (%s, %s, %s, %s, %s, %s)
    """
    data = (timestamp, car_count, bus_count, truck_count, total_count, traffic_density)
    cursor.execute(insert_query, data)
    connection.commit()
    cursor.close()
    connection.close()

# Fungsi untuk menghitung kepadatan lalu lintas dengan Q yang diambil dari total_vehicles
def calculate_traffic_density(Q, user_Co, user_Fcw, user_FCsp, user_FCsf, user_FCcs):
    # Hitung kapasitas jalan (C) dalam kendaraan per detik
    C = user_Co * user_Fcw * user_FCsp * user_FCsf * user_FCcs
    
    # Rasio V/C
    ratio = Q / C if C > 0 else 0

    # Klasifikasi A-F
    if ratio <= 0.20:
        level = "Rasio : arus lalu lintas \n bebas dengan \n kecepatan tinggi \n dan volume lalu lintas rendah"
    elif ratio <= 0.44:
        level = "Rasio : arus stabil, tetapi \n kecepatan operasi \n mulai dibatasi \n oleh kondisi lalu lintas"
    elif ratio <= 0.74:
        level = "Rasio : arus stabil, tetapi \n kecepatan dan gerak \n kendaraan dikendalikan"
    elif ratio <= 0.84:
        level = "Rasio : arus mendekati stabil, \n kecepatan masih dapat dikendalikan. \n V/C masih dapat ditolerir"
    elif ratio <= 1.0:
        level = "Rasio : arus tidak stabil, \n kecepatan terkadang terhenti, \n permintaan sudah mendekati kapasitas"
    else:
        level = "Rasio : arus dipaksakan, \n kecepatan rendah, \n volume di atas kapasitas, \n antrian panjang (macet)"

    #return f"Rasio: {level}"
    return f"{level}"

# Antarmuka aplikasi Streamlit
def main():
    st.title("JUMLAH KENDARAAN RODA EMPAT YANG MELINTAS")
    st.write("-------------------------------------------------------------------------------------")

    # Tambahkan input untuk variabel C (kapasitas jalan, dalam kendaraan/jam)
    user_Co = st.number_input("Masukkan nilai Co (kapasitas dasar (kendaraan/jam)):", min_value=1, value=2900, step=1)
    user_Fcw = st.number_input("Masukkan nilai Fcw (kapasitas untuk Jalur lalu lintas):", min_value=0.5, value=1.14, step=0.01)
    user_FCsp = st.number_input("Masukkan nilai FCsp (kapasitas untuk Pemisahan arah):", min_value=0.5, value=1.0, step=0.01)
    user_FCsf = st.number_input("Masukkan nilai FCsf (kapasitas untuk hambatan samping):", min_value=0.4, value=0.82, step=0.01)
    user_FCcs = st.number_input("Masukkan nilai FCcs (kapasitas untuk ukuran kota):", min_value=0.8, value=1.0, step=0.01)

    option = st.radio("Pilih sumber video:", ('Webcam', 'Unggah Video', 'IP Camera'))

    if option == 'Webcam':
        cap = cv2.VideoCapture(0)
        y_line = 308
    elif option == 'Unggah Video':
        uploaded_file = st.file_uploader("Unggah Video", type=['mp4'])
        if uploaded_file is not None:
            tfile = tempfile.NamedTemporaryFile(delete=False)
            tfile.write(uploaded_file.read())
            video_path = tfile.name
            cap = cv2.VideoCapture(video_path)
            fps = cap.get(cv2.CAP_PROP_FPS)  # Ambil FPS dari video
        else:
            return
        y_line = 380
    elif option == 'IP Camera':
        ip_address = st.text_input("Masukkan URL RTSP kamera:", 'rtsp://<username>:<password>@<IP_address>:<port>')
        if st.button("Connect"):
            cap = cv2.VideoCapture(ip_address)
            if not cap.isOpened():
                st.error("Tidak dapat terhubung ke IP camera. Pastikan URL RTSP benar.")
                return
        else:
            return
        y_line = 308
    else:
        st.error("Pilihan tidak valid.")
        return

    down = {}
    counter_down_car = set()
    counter_down_bus = set()
    counter_down_truck = set()

    stframe = st.empty()
    car_count_text = st.empty()
    bus_count_text = st.empty()
    truck_count_text = st.empty()
    total_count_text = st.empty()
    fps_text = st.empty()
    traffic_status_text = st.empty()
    detik_text = st.empty()
    menit_text = st.empty()
    traffic_density_text = "Rasio: -"
    flow_text = st.empty()   # Untuk menampilkan nilai Q (lalu lintas per jam)
    ratio_text = st.empty()  # Untuk menampilkan rasio Q/C

    prev_car_count = -1
    prev_bus_count = -1
    prev_truck_count = -1
    prev_total_vehicles = -1

    prev_time = time.time()
    fps = 0

    # Variabel untuk menghitung estimasi kepadatan
    start_time = time.time()

    # Variabel untuk total pengukuran selama sesi (tidak direset)
    detection_start_time_total = time.time()

    # --- Tambahan: Timer untuk looping setiap menit ---
    minute_timer = time.time()

    # Definisikan batas area deteksi (misalnya, hanya di tengah frame)
    min_x, max_x = 100, 700
    min_y, max_y = 50, 700

    menit = 0

    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break

        results = model(frame)
        vehicles_list = []
        vehicles_detected_in_frame = set()  # Gunakan set untuk menghindari duplikasi

        cv2.line(frame, (0, y_line), (frame.shape[1], y_line), (255, 0, 0), 2)

        for result in results:
            boxes = result.boxes
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                d = int(box.cls[0])
                c = class_list[d]
                if c in ['car', 'bus', 'truck']:
                    # Periksa apakah pusat bounding box berada di dalam area valid
                    cx = int((x1 + x2) / 2)
                    cy = int((y1 + y2) / 2)
                    if min_x <= cx <= max_x and min_y <= cy <= max_y:  # Filter area
                        vehicles_detected_in_frame.add((x1, y1, x2, y2))  # Tambahkan ke set
                        vehicles_list.append([x1, y1, x2, y2, c])
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        cv2.putText(frame, c, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

        # Update pelacakan kendaraan yang melewati garis
        bbox_id = tracker.update([bbox[:4] for bbox in vehicles_list])
        for i, bbox in enumerate(bbox_id):
            x3, y3, x4, y4, id = bbox
            cx = int((x3 + x4) / 2)
            cy = int((y3 + y4) / 2)
            label = vehicles_list[i][4]

            offset = 20
            if y_line - offset < cy < y_line + offset:
                if id not in down:
                    down[id] = (cy, label)
                    if label == 'car':
                        counter_down_car.add(id)
                    elif label == 'bus':
                        counter_down_bus.add(id)
                    elif label == 'truck':
                        counter_down_truck.add(id)

                cv2.circle(frame, (cx, cy), 4, (0, 0, 255), -1)

        # Hitung jumlah kendaraan yang melewati garis
        car_count = len(counter_down_car)
        bus_count = len(counter_down_bus)
        truck_count = len(counter_down_truck)
        total_vehicles = car_count + bus_count + truck_count

        # Hitung FPS secara dinamis
        curr_time = time.time()
        time_elapsed = curr_time - prev_time
        fps = 1 / time_elapsed if time_elapsed > 0 else 0
        prev_time = curr_time

        # Tampilkan hasil deteksi
        car_count_text.text(f"JUMLAH MOBIL: {car_count}")
        bus_count_text.text(f"JUMLAH BUS: {bus_count}")
        truck_count_text.text(f"JUMLAH TRUCK: {truck_count}")
        total_count_text.text(f"JUMLAH TOTAL KENDARAAN: {total_vehicles}")
        fps_text.text(f"FPS: {int(fps)}")

        if (car_count != prev_car_count or bus_count != prev_bus_count or 
            truck_count != prev_truck_count or total_vehicles != prev_total_vehicles):
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            prev_car_count = car_count
            prev_bus_count = bus_count
            prev_truck_count = truck_count
            prev_total_vehicles = total_vehicles

        detik_text.text(f"Waktu : {time.time() - minute_timer:.2f} detik")


        if time.time() - minute_timer >= 60:
            menit += 1
            Q = total_vehicles / menit * 60
            menit_text.text(f"Menit : {menit} menit, Q: {Q:.2f} kendaraan/jam")
            # Hitung kepadatan lalu lintas menggunakan total_vehicles dan detection_start_time
            traffic_density_text = calculate_traffic_density(
                Q,
                user_Co,
                user_Fcw,
                user_FCsp,
                user_FCsf,
                user_FCcs
            )
            save_to_mysql(timestamp, car_count, bus_count, truck_count, total_vehicles, traffic_density_text)
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            prev_car_count = car_count
            prev_bus_count = bus_count
            prev_truck_count = truck_count
            prev_total_vehicles = total_vehicles
            minute_timer = time.time()

        x, y = 0, 30
        line_height = 30

        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.6
        color = (255, 255, 255)  # Warna hijau (BGR)
        thickness = 2

        for i, line in enumerate(traffic_density_text.split('\n')):
            y_position = y + i * line_height  # Sesuaikan posisi y untuk setiap baris
            cv2.putText(frame, line, (x, y_position), font, font_scale, color, thickness)

        stframe.image(frame, channels="BGR", use_container_width=True)


    cap.release()

if __name__ == "__main__":
    main()