from flask import Flask, jsonify, send_from_directory, request
import sqlite3
from pathlib import Path
from datetime import date, datetime
from uuid import uuid4

app = Flask(__name__)

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "easyhotel.db"
FRONTEND_DIR = BASE_DIR / "frontend"


def get_db_connection():
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def get_room_category(room_type):
    room_type = str(room_type or "").lower()

    if "single" in room_type:
        return "Single"
    if "double" in room_type or "classic" in room_type:
        return "Double"
    if "deluxe" in room_type:
        return "Deluxe"
    if "suite" in room_type:
        return "Suite"
    if "family" in room_type:
        return "Family"

    return "Any"


@app.route("/")
def home():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/api/rooms")
def get_rooms():
    connection = get_db_connection()

    try:
        rooms = connection.execute(
            "SELECT * FROM rooms"
        ).fetchall()

        return jsonify([dict(room) for room in rooms])

    finally:
        connection.close()


@app.route("/api/health")
def health():
    return jsonify({
        "status": "success",
        "message": "EasyHotel API is running!"
    })


@app.route("/api/bookings", methods=["POST"])
def create_booking():
    data = request.get_json(silent=True) or {}

    first_name = str(data.get("first_name", "")).strip()
    last_name = str(data.get("last_name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = str(data.get("phone", "")).strip()
    check_in = str(data.get("check_in", "")).strip()
    check_out = str(data.get("check_out", "")).strip()
    room_type = str(data.get("room_type", "Any")).strip()
    special_request = str(data.get("special_request", "")).strip()

    try:
        adults = int(data.get("adults", 1))
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid number of guests."}), 400

    if not all([
        first_name, last_name, email, phone, check_in, check_out
    ]):
        return jsonify({
            "error": "Please complete all required fields."
        }), 400

    if adults < 1 or adults > 5:
        return jsonify({
            "error": "Guests must be between 1 and 5."
        }), 400

    try:
        arrival = date.fromisoformat(check_in)
        departure = date.fromisoformat(check_out)
    except ValueError:
        return jsonify({
            "error": "Please enter valid dates."
        }), 400

    if arrival < date.today():
        return jsonify({
            "error": "Check-in cannot be in the past."
        }), 400

    if departure <= arrival:
        return jsonify({
            "error": "Check-out must be after check-in."
        }), 400

    nights = (departure - arrival).days
    connection = get_db_connection()

    try:
        connection.execute("BEGIN IMMEDIATE")

        rooms = connection.execute(
            "SELECT * FROM rooms"
        ).fetchall()

        selected_room = None

        for room in rooms:
            status = str(room["status"] or "").strip().lower()

            if status in (
                "maintenance",
                "unavailable",
                "out of service"
            ):
                continue

            try:
                capacity = int(room["capacity"] or 0)
            except (ValueError, TypeError):
                capacity = 0

            if capacity < adults:
                continue

            if room_type != "Any":
                if get_room_category(room["room_type"]) != room_type:
                    continue

            existing_booking = connection.execute(
                """
                SELECT booking_id
                FROM bookings
                WHERE room_id = ?
                  AND lower(booking_status)
                      NOT IN ('cancelled', 'canceled')
                  AND check_in < ?
                  AND check_out > ?
                LIMIT 1
                """,
                (room["room_id"], check_out, check_in)
            ).fetchone()

            if existing_booking:
                continue

            selected_room = room
            break

        if selected_room is None:
            connection.rollback()
            return jsonify({
                "error": (
                    "No suitable room is available for these dates. "
                    "Please try different dates or room types."
                )
            }), 409

        guest = connection.execute(
            """
            SELECT guest_id
            FROM guests
            WHERE lower(email) = ?
            LIMIT 1
            """,
            (email,)
        ).fetchone()

        if guest:
            guest_id = guest["guest_id"]

            connection.execute(
                """
                UPDATE guests
                SET first_name = ?, last_name = ?, phone = ?
                WHERE guest_id = ?
                """,
                (first_name, last_name, phone, guest_id)
            )
        else:
            guest_id = "G-" + uuid4().hex[:12].upper()

            connection.execute(
                """
                INSERT INTO guests
                (
                    guest_id, first_name, last_name,
                    email, phone, city, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guest_id,
                    first_name,
                    last_name,
                    email,
                    phone,
                    "",
                    datetime.now().isoformat(timespec="seconds")
                )
            )

        try:
            price = float(
                selected_room["price_per_night_egp"] or 0
            )
        except (ValueError, TypeError):
            price = 0

        total_amount = round(price * nights, 2)
        booking_id = "B-" + uuid4().hex[:12].upper()

        connection.execute(
            """
            INSERT INTO bookings (
                booking_id,
                guest_id,
                room_id,
                check_in,
                check_out,
                nights,
                adults,
                children,
                booking_status,
                total_amount_egp,
                special_request
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                booking_id,
                guest_id,
                selected_room["room_id"],
                check_in,
                check_out,
                str(nights),
                str(adults),
                "0",
                "Confirmed",
                str(total_amount),
                special_request
            )
        )

        connection.commit()

        return jsonify({
            "status": "success",
            "message": "Booking saved successfully!",
            "booking_id": booking_id,
            "room_number": selected_room["room_number"],
            "room_type": selected_room["room_type"],
            "nights": nights,
            "total_amount_egp": total_amount
        }), 201

    except sqlite3.Error:
        connection.rollback()
        app.logger.exception("Booking database error.")

        return jsonify({
            "error": "Database error. Please try again."
        }), 500

    finally:
        connection.close()


if __name__ == "__main__":
    app.run(debug=True)

