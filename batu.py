import re
import json
import os
import csv
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, CallbackQueryHandler, ContextTypes, filters

# --- KONFIGURASI TOKEN BOT ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise ValueError("❌ Token Bot belum diset! Periksa kembali file .env Anda.")

JSON_FILE = "data_eshop.json"
ITEMS_PER_PAGE = 25  # Jumlah item per halaman

def parse_eshop_message(text):
    """Mengekstrak nama item dan harga dari pesan"""
    items = []
    pattern = r'/eshop_ts_([A-Za-z0-9]+)_\d+\s*-\s*([\d,]+)\s*GC'
    matches = re.findall(pattern, text)
    
    for item_name, price_str in matches:
        price_num = int(price_str.replace(',', ''))
        items.append({
            "item_name": item_name,
            "price_gc": price_num,
            "price_formatted": f"{price_str} GC"
        })
    return items

def load_existing_data(filename=JSON_FILE):
    """Membaca data yang sudah ada di file JSON"""
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return []
    return []

def save_merged_data(new_items, filename=JSON_FILE):
    """Menggabungkan data lama dengan data baru tanpa menghapus data sebelumnya"""
    existing_data = load_existing_data(filename)
    
    data_dict = {item["item_name"]: item for item in existing_data}
    for item in new_items:
        data_dict[item["item_name"]] = item
        
    updated_list = list(data_dict.values())
    
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(updated_list, f, indent=4, ensure_ascii=False)
        
    save_to_csv(updated_list)
    return len(updated_list)

def save_to_csv(data, filename="data_eshop.csv"):
    """Menyimpan data terstruktur ke format CSV"""
    if not data:
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["item_name", "price_gc", "price_formatted"])
        writer.writeheader()
        writer.writerows(data)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangkap pesan dan memperbarui data secara dinamis"""
    message = update.message
    if not message or not message.text:
        return

    text = message.text
    
    if "TokoEvent" in text or "/eshop_ts_" in text:
        extracted_data = parse_eshop_message(text)
        
        if extracted_data:
            total_items = save_merged_data(extracted_data)
            await message.reply_text(
                f"✅ Berhasil memproses pesan!\n"
                f"• Item baru ditambahkan/diperbarui: {len(extracted_data)}\n"
                f"• Total seluruh item dalam database: {total_items}\n\n"
                f"Ketik `/data` untuk melihat daftar lengkap."
            )

async def generate_data_message(page=1, sort_order="asc"):
    """
    Menyusun teks data, pagination, dan tombol pengurutan (sort).
    sort_order: 'asc' (Termurah-Termahal), 'desc' (Termahal-Termurah), atau 'alpha' (Abjad A-Z)
    """
    data = load_existing_data(JSON_FILE)

    if not data:
        return "❌ Belum ada data yang tersimpan. Kirim pesan TokoEvent terlebih dahulu.", None

    # Pengurutan data
    if sort_order == "alpha":
        data_sorted = sorted(data, key=lambda x: x['item_name'].lower())
        sort_label = "🔤 Berdasarkan Abjad (A-Z)"
    else:
        is_desc = (sort_order == "desc")
        # Jika harga sama, urutkan berdasarkan abjad (A-Z) sebagai secondary key
        data_sorted = sorted(data, key=lambda x: (x['price_gc'], x['item_name'].lower()), reverse=is_desc)
        sort_label = "📉 Termahal ➡️ Termurah" if is_desc else "📈 Termurah ➡️ Termahal"

    total_items = len(data_sorted)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if page < 1:
        page = 1
    elif page > total_pages:
        page = total_pages

    start_idx = (page - 1) * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    page_items = data_sorted[start_idx:end_idx]

    max_name_len = max(len(item['item_name']) for item in page_items)

    response_text = f"🛒 <b>Daftar Item TokoEvent</b> ({sort_label})\n(Halaman {page}/{total_pages})\n\n"
    
    for item in page_items:
        padding = " " * (max_name_len - len(item['item_name']))
        response_text += f"• <code>{item['item_name']}</code>{padding} : <b>{item['price_formatted']}</b>\n"

    # Membuat tombol navigasi & tombol ubah urutan harga
    keyboard = []
    
    # Tombol Ganti Mode Urutan
    if sort_order == "alpha":
        sort_button_text = "🔄 Ubah ke: Termurah ➡️ Termahal"
        next_sort = "asc"
    elif sort_order == "asc":
        sort_button_text = "🔄 Ubah ke: Termahal ➡️ Termurah"
        next_sort = "desc"
    else:
        sort_button_text = "🔄 Ubah ke: Abjad (A-Z)"
        next_sort = "alpha"
        
    keyboard.append([InlineKeyboardButton(sort_button_text, callback_data=f"sort_{next_sort}_1")])

    # Tombol Navigasi Halaman (Pagination)
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("⬅️ Sebelumnya", callback_data=f"sort_{sort_order}_{page - 1}"))
    
    nav_buttons.append(InlineKeyboardButton(f"📄 {page}/{total_pages}", callback_data="current_page"))
    
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Berikutnya ➡️", callback_data=f"sort_{sort_order}_{page + 1}"))
        
    if nav_buttons:
        keyboard.append(nav_buttons)
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    return response_text, reply_markup

async def show_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perintah /data (Default: Abjad A-Z)"""
    text, reply_markup = await generate_data_message(1, "alpha")
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def show_termahal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perintah /termahal"""
    text, reply_markup = await generate_data_message(1, "desc")
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def show_termurah(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perintah /termurah"""
    text, reply_markup = await generate_data_message(1, "asc")
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")

async def hitung_pembelian_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Perintah /beli [jumlah] [nama_item] untuk menghitung total harga dan diskon"""
    args = context.args
    
    if len(args) < 2:
        await update.message.reply_text(
            "❌ Format salah!\n"
            "Gunakan format: `/beli [jumlah] [nama_item]`\n"
            "Contoh: `/beli 12 acterium`",
            parse_mode="Markdown"
        )
        return

    try:
        jumlah_item = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ Jumlah item harus berupa angka. Contoh: `/beli 12 acterium`", parse_mode="Markdown")
        return

    nama_cari = " ".join(args[1:]).lower()
    
    data = load_existing_data(JSON_FILE)
    if not data:
        await update.message.reply_text("❌ Belum ada data item di database. Kirim pesan TokoEvent terlebih dahulu.")
        return

    item_ditemukan = None
    for item in data:
        if item['item_name'].lower() == nama_cari:
            item_ditemukan = item
            break

    if not item_ditemukan:
        await update.message.reply_text(f"❌ Item dengan nama *{nama_cari}* tidak ditemukan di database.", parse_mode="Markdown")
        return

    harga_satuan = item_ditemukan['price_gc']
    total_harga_dasar = harga_satuan * jumlah_item

    # Rumus Diskon
    if jumlah_item >= 20:
        persen_diskon = 60
    elif jumlah_item >= 10:
        persen_diskon = 50
    elif jumlah_item >= 5:
        persen_diskon = 40
    elif jumlah_item == 4:
        persen_diskon = 30
    elif jumlah_item == 3:
        persen_diskon = 20
    elif jumlah_item == 2:
        persen_diskon = 10
    else:
        persen_diskon = 0

    besar_potongan = int(total_harga_dasar * (persen_diskon / 100))
    total_akhir = total_harga_dasar - besar_potongan

    pesan = (
        f"🛒 <b>Simulasi Pembelian Eshop</b>\n\n"
        f"• <b>Item</b> : <code>{item_ditemukan['item_name']}</code>\n"
        f"• <b>Jumlah</b> : {jumlah_item} item\n"
        f"• <b>Harga Satuan</b> : {item_ditemukan['price_formatted']}\n"
        f"• <b>Total Harga Asli</b> : {total_harga_dasar:,} GC\n"
        f"• <b>Diskon</b> : <b>{persen_diskon}% OFF</b>\n"
        f"• <b>Besar Potongan</b> : -{besar_potongan:,} GC\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Total Bayar</b> : <b>{total_akhir:,} GC</b>"
    )

    await update.message.reply_text(pesan, parse_mode="HTML")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menangani klik tombol interaktif (pagination & sorting)"""
    query = update.callback_query
    await query.answer()

    data_callback = query.data
    
    if data_callback.startswith("sort_"):
        parts = data_callback.split("_")
        sort_order = parts[1]
        page = int(parts[2])
        
        text, reply_markup = await generate_data_message(page, sort_order)
        await query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode="HTML")

def main():
    application = ApplicationBuilder().token(TOKEN).build()

    # Daftarkan semua Command Handler
    application.add_handler(CommandHandler("data", show_data))
    application.add_handler(CommandHandler("termahal", show_termahal))
    application.add_handler(CommandHandler("termurah", show_termurah))
    application.add_handler(CommandHandler("beli", hitung_pembelian_command))
    
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    print("🚀 Bot Telegram aktif dan siap digunakan!")
    application.run_polling()

if __name__ == '__main__':
    main()