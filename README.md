# Ultimate Combolist Manager v2.0

A high-performance Python utility designed for cleaning, filtering, and organizing large-scale combolists. It features parallel processing and streaming modes to efficiently handle files exceeding several gigabytes.

## 🚀 Key Features

* **Parallel Processing:** Uses `ProcessPoolExecutor` to utilize all available CPU cores for tasks like keyword extraction and ASCII cleaning.
* **Streaming Mode:** Process massive files line-by-line to avoid "Out of Memory" crashes.
* **Smart Analysis:** Get instant statistics on total lines, unique entries, duplicate percentages, and top email domains.
* **Format Conversion:** Quickly switch between `email:pass`, `user:pass`, and fix `url:email:pass` formats.
* **Auto-Split by Domain:** Automatically categorize a massive list into separate files based on email providers (e.g., hotmail.com, gmail.com).
* **Regex Support:** Powerful filtering using custom regular expressions.

## 🛠 Installation

1.  **Clone the repository** or download `ultimate_combolist_manager2.0.py`.
2.  **Ensure Python 3.8+ is installed.**
3.  **Check Tkinter:**
    * **Windows/macOS:** Standard with Python.
    * **Linux:** Install via `sudo apt-get install python3-tk`.

## 📖 Usage

Run the script from your terminal:

```bash
python ultimate_combolist_manager2.0.py
