import cv2
import numpy as np
import pandas as pd
import easyocr
import re
from datetime import datetime
import os
from pathlib import Path
import logging
from ultralytics import YOLO
import time


class ANPRSystem:
    def __init__(self, yolo_model_path="yolov8n.pt", confidence_threshold=0.7, ocr_confidence_threshold=0.6):
        """
        Initialize ANPR System

        Args:
            yolo_model_path: Path to YOLO model for license plate detection
            confidence_threshold: Minimum confidence for plate detection
            ocr_confidence_threshold: Minimum confidence for OCR text recognition
        """
        # Setup logging
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        self.logger = logging.getLogger(__name__)

        # Initialize YOLO model
        try:
            self.yolo_model = YOLO(yolo_model_path)
            self.logger.info(f"YOLO model loaded: {yolo_model_path}")
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model: {e}")
            raise

        # Initialize EasyOCR
        try:
            self.ocr_reader = easyocr.Reader(['en'], gpu=True)  # Use GPU if available
            self.logger.info("EasyOCR initialized successfully")
        except Exception as e:
            self.logger.warning(f"GPU not available, using CPU for OCR: {e}")
            self.ocr_reader = easyocr.Reader(['en'], gpu=False)

        # Configuration
        self.confidence_threshold = confidence_threshold
        self.ocr_confidence_threshold = ocr_confidence_threshold

        # Create parking_data folder if it doesn't exist
        self.data_folder = "parking_data"
        os.makedirs(self.data_folder, exist_ok=True)
        self.csv_file = os.path.join(self.data_folder, "anpr_detections.csv")

        # Emergency vehicle patterns (can be customized)
        self.emergency_patterns = [
            r'^POLICE\d*$', r'^FIRE\d*$', r'^AMBULANCE\d*$',
            r'^EMG\d*$', r'^911\d*$', r'^999\d*$'
        ]

        # License plate validation patterns (customize for your region)
        self.plate_patterns = [
            r'^[A-Z]{2}\d{2}[A-Z]{3}$',  # UK format: AB12CDE
            r'^[A-Z]{3}\d{4}$',  # USA format: ABC1234
            r'^\d{3}[A-Z]{3}$',  # Format: 123ABC
            r'^[A-Z]{2}\d{4}[A-Z]{2}$',  # Format: AB1234CD
            r'^[A-Z]{1}\d{3}[A-Z]{3}$',  # Format: A123BCD
            r'^[A-Z]{3}\d{3}$',  # Format: ABC123
        ]

        # Initialize CSV file
        self._initialize_csv()

    def _initialize_csv(self):
        """Initialize CSV file with headers if it doesn't exist"""
        if not os.path.exists(self.csv_file):
            df = pd.DataFrame(
                columns=['id', 'plate_number', 'confidence', 'detection_time', 'is_emergency', 'processed'])
            df.to_csv(self.csv_file, index=False)
            self.logger.info(f"Created CSV file: {self.csv_file}")
        else:
            self.logger.info(f"Using existing CSV file: {self.csv_file}")

    def _clean_plate_text(self, text):
        """Clean and normalize license plate text"""
        # Remove special characters and spaces
        cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())

        # Common OCR corrections
        corrections = {
            'O': '0', 'I': '1', 'S': '5', 'Z': '2', 'B': '8', 'G': '6'
        }

        # Apply corrections only if it makes sense contextually
        result = ""
        for char in cleaned:
            if char in corrections and len(result) > 0:
                # Apply correction logic based on position and context
                if char == 'O' and (result[-1:].isdigit() or len([c for c in result if c.isdigit()]) > len(
                        [c for c in result if c.isalpha()])):
                    result += corrections[char]
                elif char == 'I' and (result[-1:].isdigit() or len([c for c in result if c.isdigit()]) > len(
                        [c for c in result if c.isalpha()])):
                    result += corrections[char]
                else:
                    result += char
            else:
                result += char

        return result

    def _validate_plate(self, plate_text):
        """Validate if the detected text is a valid license plate"""
        if len(plate_text) < 4 or len(plate_text) > 10:
            return False

        # Check against known patterns
        for pattern in self.plate_patterns:
            if re.match(pattern, plate_text):
                return True

        # Additional validation: should have both letters and numbers
        has_letter = any(c.isalpha() for c in plate_text)
        has_number = any(c.isdigit() for c in plate_text)

        return has_letter and has_number

    def _is_emergency_vehicle(self, plate_text):
        """Check if the plate belongs to an emergency vehicle"""
        for pattern in self.emergency_patterns:
            if re.match(pattern, plate_text):
                return True
        return False

    def _enhance_plate_image(self, plate_img):
        """Enhance the license plate image for better OCR"""
        # Convert to grayscale
        if len(plate_img.shape) == 3:
            gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
        else:
            gray = plate_img

        # Apply denoising
        denoised = cv2.fastNlMeansDenoising(gray)

        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(denoised, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)

        # Morphological operations to clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
        morphed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

        return morphed

    def detect_plates(self, image):
        """Detect license plates in the image using YOLO"""
        results = self.yolo_model(image, conf=self.confidence_threshold)
        plates = []

        for result in results:
            boxes = result.boxes
            if boxes is not None:
                for box in boxes:
                    confidence = float(box.conf[0])
                    if confidence >= self.confidence_threshold:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        plates.append({
                            'bbox': (x1, y1, x2, y2),
                            'confidence': confidence
                        })

        return plates

    def extract_text(self, plate_image):
        """Extract text from license plate using EasyOCR with multiple attempts"""
        best_text = ""
        best_confidence = 0

        # Try with original image
        results = self.ocr_reader.readtext(plate_image)
        for (bbox, text, confidence) in results:
            if confidence > best_confidence and len(text.strip()) >= 4:
                best_text = text.strip()
                best_confidence = confidence

        # Try with enhanced image
        enhanced_img = self._enhance_plate_image(plate_image)
        enhanced_results = self.ocr_reader.readtext(enhanced_img)
        for (bbox, text, confidence) in enhanced_results:
            if confidence > best_confidence and len(text.strip()) >= 4:
                best_text = text.strip()
                best_confidence = confidence

        # Try with different preprocessing
        resized = cv2.resize(plate_image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        resized_results = self.ocr_reader.readtext(resized)
        for (bbox, text, confidence) in resized_results:
            if confidence > best_confidence and len(text.strip()) >= 4:
                best_text = text.strip()
                best_confidence = confidence

        return best_text, best_confidence

    def process_image(self, image_path):
        """Process a single image for ANPR"""
        try:
            # Load image
            image = cv2.imread(image_path)
            if image is None:
                self.logger.error(f"Could not load image: {image_path}")
                return []

            # Detect license plates
            plates = self.detect_plates(image)
            detections = []

            for plate_info in plates:
                x1, y1, x2, y2 = plate_info['bbox']
                detection_confidence = plate_info['confidence']

                # Extract plate region
                plate_img = image[y1:y2, x1:x2]

                if plate_img.size == 0:
                    continue

                # Extract text
                plate_text, ocr_confidence = self.extract_text(plate_img)

                # Clean and validate
                cleaned_text = self._clean_plate_text(plate_text)

                if (ocr_confidence >= self.ocr_confidence_threshold and
                        self._validate_plate(cleaned_text) and
                        len(cleaned_text) >= 4):
                    # Calculate combined confidence
                    combined_confidence = (detection_confidence + ocr_confidence) / 2

                    detection = {
                        'plate_number': cleaned_text,
                        'confidence': round(combined_confidence, 3),
                        'detection_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'is_emergency': self._is_emergency_vehicle(cleaned_text),
                        'bbox': (x1, y1, x2, y2),
                        'raw_text': plate_text,
                        'ocr_confidence': round(ocr_confidence, 3),
                        'detection_confidence': round(detection_confidence, 3)
                    }

                    detections.append(detection)
                    self.logger.info(f"Detected plate: {cleaned_text} (confidence: {combined_confidence:.3f})")

            return detections

        except Exception as e:
            self.logger.error(f"Error processing image {image_path}: {e}")
            return []

    def process_camera(self, camera_id=0, display_window=True, save_detections=True, record_video=False,
                       output_video_path=None):
        """Process live camera feed for real-time ANPR"""
        cap = cv2.VideoCapture(camera_id)

        # Set camera properties for better quality
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)

        if not cap.isOpened():
            self.logger.error(f"Cannot open camera {camera_id}")
            return []

        # Setup video recording if requested
        out = None
        if record_video and output_video_path:
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = 30
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

        frame_count = 0
        all_detections = []
        last_detection_time = {}  # Track last detection time for each plate
        detection_cooldown = 5  # Seconds between saving same plate

        self.logger.info(
            "Starting live camera processing. Press 'q' to quit, 's' to save screenshot, 'r' to reset detections")

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    self.logger.error("Failed to read frame from camera")
                    break

                frame_count += 1
                current_time = time.time()

                # Process every 3rd frame for real-time performance
                if frame_count % 3 == 0:
                    # Save frame temporarily
                    temp_frame_path = "temp_camera_frame.jpg"
                    cv2.imwrite(temp_frame_path, frame)

                    # Process frame
                    detections = self.process_image(temp_frame_path)

                    # Filter detections based on cooldown period
                    valid_detections = []
                    for detection in detections:
                        plate_number = detection['plate_number']

                        # Check if we've seen this plate recently
                        if (plate_number not in last_detection_time or
                                current_time - last_detection_time[plate_number] > detection_cooldown):

                            detection['frame'] = frame_count
                            valid_detections.append(detection)
                            last_detection_time[plate_number] = current_time

                            # Save detection immediately for real-time processing
                            if save_detections:
                                self.save_detections([detection])

                    all_detections.extend(valid_detections)

                    # Draw all current detections on frame
                    for detection in detections:
                        x1, y1, x2, y2 = detection['bbox']

                        # Choose color based on detection type
                        if detection['is_emergency']:
                            color = (0, 0, 255)  # Red for emergency
                            thickness = 3
                        else:
                            color = (0, 255, 0)  # Green for regular
                            thickness = 2

                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

                        # Prepare label
                        label = f"{detection['plate_number']}"
                        confidence_label = f"Conf: {detection['confidence']:.2f}"

                        if detection['is_emergency']:
                            emergency_label = "[EMERGENCY]"
                            cv2.putText(frame, emergency_label, (x1, y1 - 40),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)

                        # Draw labels
                        cv2.putText(frame, label, (x1, y1 - 20),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                        cv2.putText(frame, confidence_label, (x1, y1 - 5),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

                    # Clean up temp file
                    if os.path.exists(temp_frame_path):
                        os.remove(temp_frame_path)

                # Add info overlay
                info_text = f"Detections: {len(all_detections)} | Frame: {frame_count} | Press 'q' to quit"
                cv2.putText(frame, info_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

                # Add timestamp
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                cv2.putText(frame, timestamp, (10, frame.shape[0] - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)

                # Record video if enabled
                if out is not None:
                    out.write(frame)

                # Display frame
                if display_window:
                    cv2.imshow('Live ANPR System', frame)

                # Handle key presses
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    self.logger.info("Quit requested by user")
                    break
                elif key == ord('s'):
                    screenshot_path = os.path.join(self.data_folder,
                                                   f"anpr_screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
                    cv2.imwrite(screenshot_path, frame)
                    self.logger.info(f"Screenshot saved: {screenshot_path}")
                elif key == ord('r'):
                    all_detections.clear()
                    last_detection_time.clear()
                    self.logger.info("Detection history reset")
                elif key == ord('p'):
                    # Pause/unpause
                    self.logger.info("Paused. Press any key to continue...")
                    cv2.waitKey(0)

        except KeyboardInterrupt:
            self.logger.info("Interrupted by user")
        except Exception as e:
            self.logger.error(f"Error during camera processing: {e}")
        finally:
            # Cleanup
            cap.release()
            if out is not None:
                out.release()
            if display_window:
                cv2.destroyAllWindows()

        self.logger.info(f"Camera processing completed. Total detections: {len(all_detections)}")
        return all_detections

    def process_video(self, video_path, output_video_path=None, save_detections=True):
        """Process video file for ANPR"""
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            self.logger.error(f"Cannot open video file: {video_path}")
            return []

        if output_video_path:
            # Setup video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            fps = int(cap.get(cv2.CAP_PROP_FPS))
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

        frame_count = 0
        all_detections = []

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1

            # Process every 5th frame to improve performance
            if frame_count % 5 == 0:
                # Save frame temporarily
                temp_frame_path = "temp_frame.jpg"
                cv2.imwrite(temp_frame_path, frame)

                # Process frame
                detections = self.process_image(temp_frame_path)

                # Add frame info to detections
                for detection in detections:
                    detection['frame'] = frame_count
                    all_detections.append(detection)

                # Draw detections on frame
                for detection in detections:
                    x1, y1, x2, y2 = detection['bbox']
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

                    label = f"{detection['plate_number']} ({detection['confidence']:.2f})"
                    if detection['is_emergency']:
                        label += " [EMERGENCY]"
                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 0, 255), 3)

                    cv2.putText(frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                # Clean up
                if os.path.exists(temp_frame_path):
                    os.remove(temp_frame_path)

            # Write frame to output video
            if output_video_path:
                out.write(frame)

            # Display frame (optional)
            cv2.imshow('ANPR System', cv2.resize(frame, (800, 600)))
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

        cap.release()
        if output_video_path:
            out.release()
        cv2.destroyAllWindows()

        # Save detections
        if save_detections and all_detections:
            self.save_detections(all_detections)

        return all_detections

    def save_detections(self, detections):
        """Save detections to CSV file"""
        try:
            # Load existing data
            if os.path.exists(self.csv_file):
                existing_df = pd.read_csv(self.csv_file)
                next_id = existing_df['id'].max() + 1 if not existing_df.empty else 1
            else:
                existing_df = pd.DataFrame()
                next_id = 1

            # Prepare new data
            new_data = []
            for detection in detections:
                new_data.append({
                    'id': next_id,
                    'plate_number': detection['plate_number'],
                    'confidence': detection['confidence'],
                    'detection_time': detection['detection_time'],
                    'is_emergency': detection['is_emergency'],
                    'processed': False
                })
                next_id += 1

            # Create DataFrame and append
            new_df = pd.DataFrame(new_data)
            final_df = pd.concat([existing_df, new_df], ignore_index=True)

            # Remove duplicates based on plate number and time (within 5 seconds)
            final_df['detection_time'] = pd.to_datetime(final_df['detection_time'])
            final_df = final_df.sort_values('detection_time')

            # Save to CSV
            final_df.to_csv(self.csv_file, index=False)
            self.logger.info(f"Saved {len(new_data)} detections to {self.csv_file}")

        except Exception as e:
            self.logger.error(f"Error saving detections: {e}")

    def get_detection_stats(self):
        """Get statistics from detection database"""
        try:
            df = pd.read_csv(self.csv_file)
            stats = {
                'total_detections': len(df),
                'emergency_vehicles': len(df[df['is_emergency'] == True]),
                'processed': len(df[df['processed'] == True]),
                'unprocessed': len(df[df['processed'] == False]),
                'average_confidence': df['confidence'].mean(),
                'latest_detection': df['detection_time'].max() if not df.empty else None
            }
            return stats
        except Exception as e:
            self.logger.error(f"Error getting stats: {e}")
            return None


# Camera-focused usage examples
def main():
    # Initialize ANPR system
    anpr = ANPRSystem(
        confidence_threshold=0.6,
        ocr_confidence_threshold=0.5
    )

    print("ANPR System Menu:")
    print("1. Live Camera Processing")
    print("2. Process Image")
    print("3. Process Video")
    print("4. View Detection Statistics")
    print("5. Exit")

    while True:
        choice = input("\nEnter your choice (1-5): ").strip()

        if choice == '1':
            # Live camera processing
            print("\nStarting live camera processing...")
            print("Controls:")
            print("- Press 'q' to quit")
            print("- Press 's' to save screenshot")
            print("- Press 'r' to reset detection history")
            print("- Press 'p' to pause/unpause")

            # Ask for camera options
            camera_id = input("Enter camera ID (0 for default, 1 for external): ").strip()
            camera_id = int(camera_id) if camera_id.isdigit() else 0

            record = input("Record video? (y/n): ").strip().lower() == 'y'
            output_path = None
            if record:
                output_path = os.path.join(anpr.data_folder,
                                           f"anpr_recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")

            try:
                detections = anpr.process_camera(
                    camera_id=camera_id,
                    display_window=True,
                    save_detections=True,
                    record_video=record,
                    output_video_path=output_path
                )
                print(f"\nCamera session completed. Total detections: {len(detections)}")
                if record and output_path:
                    print(f"Video saved as: {output_path}")

            except Exception as e:
                print(f"Error during camera processing: {e}")

        elif choice == '2':
            # Process image
            image_path = input("Enter image path: ").strip()
            if os.path.exists(image_path):
                print("Processing image...")
                detections = anpr.process_image(image_path)
                if detections:
                    anpr.save_detections(detections)
                    print(f"Found {len(detections)} license plates:")
                    for det in detections:
                        print(f"  - {det['plate_number']} (confidence: {det['confidence']:.3f})")
                else:
                    print("No license plates detected")
            else:
                print("Image file not found!")

        elif choice == '3':
            # Process video
            video_path = input("Enter video path: ").strip()
            if os.path.exists(video_path):
                save_output = input("Save annotated video? (y/n): ").strip().lower() == 'y'
                output_path = None
                if save_output:
                    output_path = os.path.join(anpr.data_folder,
                                               f"anpr_output_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")

                print("Processing video...")
                detections = anpr.process_video(video_path, output_path)
                print(f"Processed video with {len(detections)} total detections")
                if save_output:
                    print(f"Annotated video saved as: {output_path}")
            else:
                print("Video file not found!")

        elif choice == '4':
            # View statistics
            stats = anpr.get_detection_stats()
            if stats:
                print("\n=== Detection Statistics ===")
                print(f"Total detections: {stats['total_detections']}")
                print(f"Emergency vehicles: {stats['emergency_vehicles']}")
                print(f"Processed: {stats['processed']}")
                print(f"Unprocessed: {stats['unprocessed']}")
                print(f"Average confidence: {stats['average_confidence']:.3f}")
                print(f"Latest detection: {stats['latest_detection']}")

                # Show recent detections
                if os.path.exists(anpr.csv_file):
                    df = pd.read_csv(anpr.csv_file)
                    if not df.empty:
                        print("\n=== Recent Detections ===")
                        recent = df.tail(10)[['plate_number', 'confidence', 'detection_time', 'is_emergency']]
                        print(recent.to_string(index=False))
            else:
                print("No detection data available")

        elif choice == '5':
            print("Exiting...")
            break

        else:
            print("Invalid choice. Please enter 1-5.")


# Simple camera test function
def test_camera():
    """Simple function to test camera connectivity"""
    print("Testing camera connectivity...")

    for i in range(3):  # Test cameras 0, 1, 2
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            print(f"Camera {i}: Available")
            ret, frame = cap.read()
            if ret:
                print(f"  - Resolution: {frame.shape[1]}x{frame.shape[0]}")
                print(f"  - FPS: {cap.get(cv2.CAP_PROP_FPS)}")
            cap.release()
        else:
            print(f"Camera {i}: Not available")


if __name__ == "__main__":
    # Test camera first
    test_camera()
    print("\n" + "=" * 50)

    # Run main application
    main()