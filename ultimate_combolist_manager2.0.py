import os
import random
import re
import multiprocessing
import json
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from tkinter import filedialog, Tk

class BatchProcessor:
    @staticmethod
    def _process_chunk(lines, task_type, params=None):
        results = []
        if task_type == "extract":
            keywords = params
            for line in lines:
                if any(kw.lower() in line.lower() for kw in keywords):
                    results.append(line)
        elif task_type == "clean":
            for line in lines:
                results.append(line.encode("ascii", "ignore").decode())
        elif task_type == "convert_userpass":
            for line in lines:
                if ':' in line:
                    parts = line.strip().split(':')
                    user = parts[0].split('@')[0]
                    results.append(f"{user}:{parts[1]}\n")
        elif task_type == "filter_len":
            min_l, max_l = params
            for line in lines:
                if min_l <= len(line.strip()) <= max_l:
                    results.append(line)
        return results

class ConfigManager:
    def __init__(self, config_file='combolist_config.json'):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except:
                return self.get_default_config()
        return self.get_default_config()
    
    def get_default_config(self):
        return {
            'default_output_dir': 'output',
            'default_chunk_size': 10000,
            'max_workers': multiprocessing.cpu_count(),
            'recent_files': []
        }
    
    def save_config(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def add_recent_file(self, filepath):
        if filepath not in self.config['recent_files']:
            self.config['recent_files'].insert(0, filepath)
            self.config['recent_files'] = self.config['recent_files'][:10]  # Keep last 10
            self.save_config()

class KeywordTool:
    def __init__(self):
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.output_dir = self.config['default_output_dir']
        self.cores = self.config['max_workers']
        self.chunk_size = self.config['default_chunk_size']
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def safe_file_operation(self, func, *args, **kwargs):
        """Wrapper for file operations with error handling"""
        try:
            return func(*args, **kwargs)
        except FileNotFoundError:
            print("[ERROR] File not found!")
        except PermissionError:
            print("[ERROR] Permission denied!")
        except Exception as e:
            print(f"[ERROR] {str(e)}")
        return None

    def show_progress(self, current, total, bar_length=50, prefix=""):
        """Simple progress bar"""
        if total == 0:
            return
        percent = current / total
        arrow = '=' * int(round(percent * bar_length))
        spaces = ' ' * (bar_length - len(arrow))
        print(f"\r{prefix} [{arrow}{spaces}] {percent:.1%}", end='', flush=True)
        if current >= total:
            print()

    def select_file(self):
        root = Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        
        # Show recent files
        if self.config['recent_files']:
            print("\nRecent files:")
            for i, f in enumerate(self.config['recent_files'][:5], 1):
                print(f"  [{i}] {os.path.basename(f)}")
            print("  [0] Browse for new file")
            choice = input("\nSelect recent file (0 to browse): ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(self.config['recent_files'][:5]):
                path = self.config['recent_files'][int(choice)-1]
                root.destroy()
                return path
        
        path = filedialog.askopenfilename(title="Select File", filetypes=[("Text", "*.txt"), ("All", "*.*")])
        root.destroy()
        
        if path:
            self.config_manager.add_recent_file(path)
        return path

    def _save_file(self, filename, lines, subfolder=""):
        target_dir = os.path.join(self.output_dir, subfolder)
        if not os.path.exists(target_dir): 
            os.makedirs(target_dir)
        
        path = os.path.join(target_dir, filename if filename.endswith(".txt") else f"{filename}.txt")
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return path

    def _save_temp(self, lines):
        """Save temporary chunk file"""
        temp_dir = os.path.join(self.output_dir, "temp")
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
        
        temp_file = os.path.join(temp_dir, f"temp_{random.randint(1000, 9999)}.txt")
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        return temp_file

    def _merge_temp_files(self, temp_files):
        """Merge temporary files into final result"""
        all_lines = []
        for temp_file in temp_files:
            with open(temp_file, 'r', encoding='utf-8') as f:
                all_lines.extend(f.readlines())
            os.remove(temp_file)  # Clean up temp file
        
        # Remove temp directory if empty
        temp_dir = os.path.join(self.output_dir, "temp")
        if os.path.exists(temp_dir) and not os.listdir(temp_dir):
            os.rmdir(temp_dir)
        
        return all_lines

    def stream_process_file(self, input_path, output_path, processor_func, chunk_size=None):
        """Process large files line by line in chunks"""
        if chunk_size is None:
            chunk_size = self.chunk_size
            
        try:
            # Get total lines for progress
            with open(input_path, 'r', encoding='utf-8', errors='ignore') as f:
                total_lines = sum(1 for _ in f)
            
            processed_lines = 0
            with open(input_path, 'r', encoding='utf-8', errors='ignore') as infile:
                with open(output_path, 'w', encoding='utf-8') as outfile:
                    chunk = []
                    for line in infile:
                        chunk.append(line)
                        if len(chunk) >= chunk_size:
                            processed = processor_func(chunk)
                            outfile.writelines(processed)
                            processed_lines += len(chunk)
                            self.show_progress(processed_lines, total_lines, prefix="Processing")
                            chunk = []
                    
                    if chunk:  # Process remaining lines
                        processed = processor_func(chunk)
                        outfile.writelines(processed)
                        self.show_progress(total_lines, total_lines, prefix="Processing")
            return True
        except Exception as e:
            print(f"\n[ERROR] Streaming failed: {str(e)}")
            return False

    def validate_format(self, lines, expected_format='email:pass'):
        """Validate line format"""
        if not lines:
            return True
            
        valid = 0
        invalid = 0
        sample_size = min(100, len(lines))
        
        for line in lines[:sample_size]:
            line = line.strip()
            if expected_format == 'email:pass' and ':' in line and '@' in line.split(':')[0]:
                valid += 1
            else:
                invalid += 1
        
        if invalid > valid:
            print(f"\n[!] Warning: Format check")
            print(f"    Valid lines: {valid}/{sample_size}")
            print(f"    Invalid lines: {invalid}/{sample_size}")
            confirm = input("    Continue anyway? (y/n): ")
            return confirm.lower() == 'y'
        return True

    def _run_parallel(self, filepath, task_type, params=None):
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        # Validate format for certain operations
        if task_type in ["convert_userpass"]:
            if not self.validate_format(all_lines):
                return []
        
        chunk_size = max(1, len(all_lines) // self.cores)
        chunks = [all_lines[i:i + chunk_size] for i in range(0, len(all_lines), chunk_size)]
        
        final_results = []
        with ProcessPoolExecutor(max_workers=self.cores) as executor:
            futures = [executor.submit(BatchProcessor._process_chunk, chunk, task_type, params) for chunk in chunks]
            
            completed = 0
            for future in futures:
                final_results.extend(future.result())
                completed += 1
                self.show_progress(completed, len(futures), prefix="Parallel processing")
        
        return final_results

    def _run_parallel_streaming(self, filepath, task_type, params=None):
        """Streaming parallel processing for very large files"""
        temp_files = []
        
        try:
            # Get total lines for progress
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                total_lines = sum(1 for _ in f)
            
            processed_lines = 0
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                chunk = []
                for line in f:
                    chunk.append(line)
                    if len(chunk) >= self.chunk_size:
                        # Process chunk in separate process
                        with ProcessPoolExecutor(max_workers=self.cores) as executor:
                            future = executor.submit(BatchProcessor._process_chunk, chunk, task_type, params)
                            temp = self._save_temp(future.result())
                            temp_files.append(temp)
                        
                        processed_lines += len(chunk)
                        self.show_progress(processed_lines, total_lines, prefix="Streaming")
                        chunk = []
                
                if chunk:  # Process remaining
                    with ProcessPoolExecutor(max_workers=self.cores) as executor:
                        future = executor.submit(BatchProcessor._process_chunk, chunk, task_type, params)
                        temp = self._save_temp(future.result())
                        temp_files.append(temp)
                    self.show_progress(total_lines, total_lines, prefix="Streaming")
            
            # Merge temp files
            return self._merge_temp_files(temp_files)
            
        except Exception as e:
            print(f"\n[ERROR] Streaming parallel processing failed: {str(e)}")
            # Clean up temp files
            for temp_file in temp_files:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            return []

    def analyze_file(self, lines):
        """Enhanced file analysis"""
        if not lines:
            return None
            
        total = len(lines)
        stripped_lines = [l.strip() for l in lines if l.strip()]
        unique = len(set(stripped_lines))
        duplicates = total - unique
        
        # Email format validation
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        valid_emails = 0
        domains = []
        password_lengths = []
        
        for line in stripped_lines:
            # Check for email in first part before colon
            if ':' in line:
                email_part = line.split(':')[0]
                if re.search(email_pattern, email_part):
                    valid_emails += 1
                    
                    # Extract domain
                    domain_match = re.search(r'@([\w\.-]+)', email_part)
                    if domain_match:
                        domains.append(domain_match.group(1).lower())
                    
                    # Password analysis
                    pass_part = line.split(':')[-1]
                    password_lengths.append(len(pass_part))
        
        domain_stats = Counter(domains).most_common(10) if domains else []
        
        stats = {
            'total': total,
            'unique': unique,
            'duplicates': duplicates,
            'duplicate_pct': (duplicates/total*100) if total else 0,
            'valid_emails': valid_emails,
            'valid_pct': (valid_emails/total*100) if total else 0,
            'top_domains': domain_stats,
            'avg_pass_len': sum(password_lengths)/len(password_lengths) if password_lengths else 0,
            'sample_lines': stripped_lines[:5]  # Show first 5 lines as sample
        }
        return stats

def main():
    tool = KeywordTool()
    
    while True:
        print("\n" + "═"*65)
        print("           ULTIMATE COMBOLIST MANAGER v2.0     ")
        print("═"*65)
        print(f"Output Dir: {tool.output_dir} | Cores: {tool.cores} | Chunk: {tool.chunk_size}")
        print("\n")
        print("[1]  Split File (By Lines)  [2]  Combine Files")
        print("[3]  Randomize Lines         [4]  Remove Duplicates")
        print("[5]  Sort A-Z                [6]  Email:Pass -> User:Pass")
        print("[7]  URL:Email:Pass Fix      [8]  Keyword Extraction")
        print("[9]  Clean Non-ASCII         [10] Analyze File")
        print("[11] Filter by Length        [12] Filter by Domain")
        print("[13] Lowercase All Lines     [14] AUTO-SPLIT BY DOMAIN")
        print("[15] Regex Filter            [16] Settings")
        print("[0]  Exit")
        
        cmd = input("\nSelect Action: ").strip()
        if cmd == '0': 
            tool.config_manager.save_config()
            break

        if cmd in ['1', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15']:
            f_path = tool.select_file()
            if not f_path: 
                print("[!] No file selected")
                continue
            
            # Check file size for streaming recommendation
            file_size = os.path.getsize(f_path) / (1024 * 1024)  # MB
            if file_size > 100:  # >100MB
                print(f"[!] Large file detected ({file_size:.1f}MB)")
                use_streaming = input("    Use streaming mode? (y/n): ").strip().lower() == 'y'
            else:
                use_streaming = False
            
            save_name = ""
            if cmd not in ['1', '10', '14']:
                save_name = input("Enter output filename (no extension): ").strip()
                if not save_name:
                    print("[!] No filename provided")
                    continue

            if cmd == '1':  # Split File
                try:
                    count = int(input("Lines per file: "))
                    with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    
                    total_files = len(lines) // count + (1 if len(lines) % count else 0)
                    for i in range(0, len(lines), count):
                        tool._save_file(f"split_{i//count}", lines[i:i + count])
                        tool.show_progress(i//count + 1, total_files, prefix="Splitting")
                    print(f"\n[✔] Split into {total_files} files.")
                except ValueError:
                    print("[ERROR] Invalid number")

            elif cmd == '3':  # Randomize
                def process_chunk(chunk):
                    random.shuffle(chunk)
                    return chunk
                
                if use_streaming:
                    output_path = os.path.join(tool.output_dir, f"{save_name}.txt")
                    success = tool.stream_process_file(f_path, output_path, process_chunk)
                    if success:
                        print(f"\n[✔] File randomized and saved to {output_path}")
                else:
                    with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    random.shuffle(lines)
                    path = tool._save_file(save_name, lines)
                    print(f"[✔] File randomized and saved to {path}")

            elif cmd == '4':  # Remove Duplicates
                def process_chunk(chunk):
                    return list(dict.fromkeys(chunk))
                
                if use_streaming:
                    output_path = os.path.join(tool.output_dir, f"{save_name}.txt")
                    success = tool.stream_process_file(f_path, output_path, process_chunk)
                    if success:
                        print(f"\n[✔] Duplicates removed and saved to {output_path}")
                else:
                    with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    unique_lines = list(dict.fromkeys(lines))
                    removed = len(lines) - len(unique_lines)
                    path = tool._save_file(save_name, unique_lines)
                    print(f"[✔] Removed {removed} duplicates. Saved to {path}")

            elif cmd == '5':  # Sort A-Z
                def process_chunk(chunk):
                    return sorted(chunk)
                
                if use_streaming:
                    output_path = os.path.join(tool.output_dir, f"{save_name}.txt")
                    success = tool.stream_process_file(f_path, output_path, process_chunk)
                    if success:
                        print(f"\n[✔] File sorted and saved to {output_path}")
                else:
                    with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    path = tool._save_file(save_name, sorted(lines))
                    print(f"[✔] File sorted and saved to {path}")

            elif cmd == '6':  # Convert to User:Pass
                if use_streaming:
                    results = tool._run_parallel_streaming(f_path, "convert_userpass")
                else:
                    results = tool._run_parallel(f_path, "convert_userpass")
                
                if results:
                    path = tool._save_file(save_name, results)
                    print(f"[✔] Converted {len(results)} lines. Saved to {path}")

            elif cmd == '7':  # URL:Email:Pass Fix
                def process_chunk(chunk):
                    cleaned = []
                    for line in chunk:
                        parts = line.strip().split(':')
                        if len(parts) >= 3:
                            cleaned.append(f"{parts[-2]}:{parts[-1]}\n")
                    return cleaned
                
                if use_streaming:
                    output_path = os.path.join(tool.output_dir, f"{save_name}.txt")
                    success = tool.stream_process_file(f_path, output_path, process_chunk)
                    if success:
                        print(f"\n[✔] URLs fixed and saved to {output_path}")
                else:
                    cleaned = []
                    with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                        for line in f:
                            parts = line.strip().split(':')
                            if len(parts) >= 3:
                                cleaned.append(f"{parts[-2]}:{parts[-1]}\n")
                    path = tool._save_file(save_name, cleaned)
                    print(f"[✔] Fixed {len(cleaned)} lines. Saved to {path}")

            elif cmd == '8':  # Keyword Extraction
                kws = input("Keywords (comma separated): ").split(',')
                keywords = [k.strip() for k in kws if k.strip()]
                
                if not keywords:
                    print("[ERROR] No keywords provided")
                    continue
                
                if use_streaming:
                    results = tool._run_parallel_streaming(f_path, "extract", keywords)
                else:
                    results = tool._run_parallel(f_path, "extract", keywords)
                
                if results:
                    path = tool._save_file(save_name, results)
                    print(f"[✔] Found {len(results)} lines with keywords. Saved to {path}")

            elif cmd == '9':  # Clean Non-ASCII
                if use_streaming:
                    results = tool._run_parallel_streaming(f_path, "clean")
                else:
                    results = tool._run_parallel(f_path, "clean")
                
                if results:
                    path = tool._save_file(save_name, results)
                    print(f"[✔] Cleaned {len(results)} lines. Saved to {path}")

            elif cmd == '10':  # Analyze File
                print("\n[*] Analyzing file...")
                with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                
                stats = tool.analyze_file(lines)
                if stats:
                    print("\n" + "═"*50)
                    print("FILE ANALYSIS RESULTS")
                    print("═"*50)
                    print(f"Total Lines: {stats['total']:,}")
                    print(f"Unique Lines: {stats['unique']:,}")
                    print(f"Duplicates: {stats['duplicates']:,} ({stats['duplicate_pct']:.1f}%)")
                    print(f"Valid Email Formats: {stats['valid_emails']:,} ({stats['valid_pct']:.1f}%)")
                    print(f"Average Password Length: {stats['avg_pass_len']:.1f}")
                    
                    if stats['top_domains']:
                        print("\nTop 10 Domains:")
                        for domain, count in stats['top_domains']:
                            print(f"  {domain}: {count:,}")
                    
                    print("\nSample Lines (first 5):")
                    for i, line in enumerate(stats['sample_lines'], 1):
                        print(f"  {i}. {line[:50]}{'...' if len(line) > 50 else ''}")

            elif cmd == '11':  # Filter by Length
                try:
                    min_l = int(input("Min length: "))
                    max_l = int(input("Max length: "))
                    
                    if use_streaming:
                        results = tool._run_parallel_streaming(f_path, "filter_len", (min_l, max_l))
                    else:
                        results = tool._run_parallel(f_path, "filter_len", (min_l, max_l))
                    
                    if results:
                        path = tool._save_file(save_name, results)
                        print(f"[✔] Found {len(results)} lines. Saved to {path}")
                except ValueError:
                    print("[ERROR] Invalid length values")

            elif cmd == '12':  # Filter by Domain
                target = input("Target domain (e.g., hotmail.com): ").strip().lower()
                if not target:
                    print("[ERROR] No domain provided")
                    continue
                
                matched = []
                with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                    total_lines = sum(1 for _ in f)
                    f.seek(0)
                    
                    for i, line in enumerate(f):
                        if f"@{target}" in line.lower():
                            matched.append(line)
                        if i % 10000 == 0:
                            tool.show_progress(i, total_lines, prefix="Filtering")
                
                if matched:
                    path = tool._save_file(save_name, matched)
                    print(f"\n[✔] Found {len(matched)} lines. Saved to {path}")
                else:
                    print(f"\n[!] No lines found with domain @{target}")

            elif cmd == '13':  # Lowercase All Lines
                def process_chunk(chunk):
                    return [l.lower() for l in chunk]
                
                if use_streaming:
                    output_path = os.path.join(tool.output_dir, f"{save_name}.txt")
                    success = tool.stream_process_file(f_path, output_path, process_chunk)
                    if success:
                        print(f"\n[✔] Converted to lowercase. Saved to {output_path}")
                else:
                    with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                        lines = f.readlines()
                    path = tool._save_file(save_name, [l.lower() for l in lines])
                    print(f"[✔] Converted to lowercase. Saved to {path}")

            elif cmd == '14':  # AUTO-SPLIT BY DOMAIN
                print("[*] Sorting by domain... this may take a moment for large files.")
                domain_map = {}
                
                with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                    total_lines = sum(1 for _ in f)
                    f.seek(0)
                    
                    for i, line in enumerate(f):
                        match = re.search(r'@([\w\.-]+)', line)
                        if match:
                            dom = match.group(1).lower()
                            if dom not in domain_map:
                                domain_map[dom] = []
                            domain_map[dom].append(line)
                        
                        if i % 10000 == 0:
                            tool.show_progress(i, total_lines, prefix="Sorting")
                
                print("\n[*] Saving domain files...")
                total_domains = len(domain_map)
                for i, (domain, domain_lines) in enumerate(domain_map.items()):
                    tool._save_file(domain, domain_lines, subfolder="domains")
                    tool.show_progress(i + 1, total_domains, prefix="Saving")
                
                print(f"\n[✔] Success! Created {total_domains} files in output/domains/")

            elif cmd == '15':  # Regex Filter
                pattern = input("Enter regex pattern: ").strip()
                if not pattern:
                    print("[ERROR] No pattern provided")
                    continue
                    
                try:
                    re.compile(pattern)  # Validate regex
                    
                    matched = []
                    with open(f_path, 'r', encoding='utf-8', errors='ignore') as f:
                        total_lines = sum(1 for _ in f)
                        f.seek(0)
                        
                        for i, line in enumerate(f):
                            if re.search(pattern, line, re.IGNORECASE):
                                matched.append(line)
                            if i % 10000 == 0:
                                tool.show_progress(i, total_lines, prefix="Matching")
                    
                    if matched:
                        path = tool._save_file(save_name, matched)
                        print(f"\n[✔] Found {len(matched)} matches. Saved to {path}")
                    else:
                        print(f"\n[!] No matches found for pattern: {pattern}")
                        
                except re.error as e:
                    print(f"[ERROR] Invalid regex pattern: {str(e)}")

        elif cmd == '2':  # Combine Files
            root = Tk()
            root.withdraw()
            files = filedialog.askopenfilenames(title="Select Files to Merge")
            root.destroy()
            
            if files:
                print(f"[*] Merging {len(files)} files...")
                combined = []
                total_files = len(files)
                
                for i, f in enumerate(files):
                    with open(f, 'r', encoding='utf-8', errors='ignore') as src:
                        lines = src.readlines()
                        combined.extend(lines)
                    tool.show_progress(i + 1, total_files, prefix="Merging")
                
                name = input("\nEnter name for merged file: ").strip()
                if name:
                    path = tool._save_file(name, combined)
                    print(f"[✔] Merged {len(combined)} lines. Saved to {path}")
                else:
                    print("[!] No filename provided")

        elif cmd == '16':  # Settings
            print("\n" + "═"*50)
            print("SETTINGS")
            print("═"*50)
            print(f"1. Output Directory: {tool.output_dir}")
            print(f"2. Chunk Size: {tool.chunk_size}")
            print(f"3. Max Workers: {tool.cores}")
            print("4. Clear Recent Files")
            print("5. Back to Main Menu")
            
            setting_cmd = input("\nSelect setting to change: ").strip()
            
            if setting_cmd == '1':
                new_dir = input("Enter new output directory: ").strip()
                if new_dir:
                    tool.output_dir = new_dir
                    tool.config['default_output_dir'] = new_dir
                    if not os.path.exists(new_dir):
                        os.makedirs(new_dir)
                    print(f"[✔] Output directory updated to {new_dir}")
            
            elif setting_cmd == '2':
                try:
                    new_chunk = int(input("Enter new chunk size: "))
                    if new_chunk > 0:
                        tool.chunk_size = new_chunk
                        tool.config['default_chunk_size'] = new_chunk
                        print(f"[✔] Chunk size updated to {new_chunk}")
                except ValueError:
                    print("[ERROR] Invalid number")
            
            elif setting_cmd == '3':
                try:
                    new_cores = int(input(f"Enter new worker count (max {multiprocessing.cpu_count()}): "))
                    if 1 <= new_cores <= multiprocessing.cpu_count():
                        tool.cores = new_cores
                        tool.config['max_workers'] = new_cores
                        print(f"[✔] Worker count updated to {new_cores}")
                except ValueError:
                    print("[ERROR] Invalid number")
            
            elif setting_cmd == '4':
                tool.config['recent_files'] = []
                print("[✔] Recent files cleared")
            
            tool.config_manager.save_config()

        else:
            print("[!] Invalid option. Please try again.")

if __name__ == "__main__":
    main()