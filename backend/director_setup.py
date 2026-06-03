"""
Alat bantu LOKAL untuk menyiapkan kredensial Direktur (MFA TOTP) saat menguji /director-dashboard.

Jalankan DI FOLDER backend (env yang SAMA dengan server — folder & CDSS_SECRET_KEY sama):
    python director_setup.py

Mencetak:
  1) otpauth:// URI  -> pindai ke Google Authenticator / Authy / Microsoft Authenticator, ATAU
  2) KODE 6-digit SAAT INI -> untuk uji cepat tanpa aplikasi (berlaku ~30 detik).

CATATAN: ini hanya ALAT UJI LOKAL. Jangan dipakai untuk membocorkan kode di produksi.
"""
import time
import director

sec, new = director.ensure_secret()
print("== Setup Direktur (MFA TOTP) ==")
print("Secret:", "BARU dibuat & disimpan terenkripsi (.director_totp)" if new else "sudah ada (.director_totp)")
print()
print("otpauth URI (pindai ke aplikasi authenticator):")
print("  " + director.otpauth_uri())
print()
code = director._totp(sec, time.time())
remaining = 30 - int(time.time()) % 30
print(f"KODE TOTP SAAT INI : {code}   (berlaku ~{remaining} detik)")
print()
print("Lalu buka http://localhost:3000/director-dashboard dan masukkan kode 6-digit di atas.")
