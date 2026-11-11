import paramiko
import threading
import logging
import socket
import time
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

LOG_FILE = "output.log"
TIMEOUT = 15
RETRY_COUNT = 5
RETRY_DELAY = 5

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format="%(asctime)s - %(message)s")
successful_hosts = 0
failed_hosts = 0
lock = threading.Lock()


def clear_log():
    """Clear the log file and reset success/failure counters"""
    open(LOG_FILE, "w").close()
    global successful_hosts, failed_hosts
    successful_hosts = 0
    failed_hosts = 0  # Reset success and failure counters


def read_hosts(file_path, format_type):
    """Read host information from a text file, supports different formats"""
    hosts = []
    try:
        with open(file_path, "r") as file:
            for line in file:
                line = line.strip()
                if line:
                    try:
                        if format_type == "hostname:port:username:password":
                            hostname, port, username, password = line.split(":")
                        elif format_type == "hostname username password port":
                            hostname, username, password, port = line.split()
                        else:
                            logging.error(f"Unknown format: {format_type}")
                            return hosts

                        hosts.append(
                            {
                                "hostname": hostname,
                                "port": int(port),
                                "username": username,
                                "password": password
                            }
                        )
                    except ValueError:
                        logging.error(f"Invalid line format: {line}")
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
    except Exception as e:
        logging.error(f"Error reading file: {e}")
    return hosts


def check_connection(hostname, port):
    """Check host port availability"""
    try:
        socket.create_connection((hostname, port), timeout=TIMEOUT)
        return True
    except (socket.timeout, ConnectionRefusedError, OSError):
        return False


def execute_command(host_info, command):
    """Connect to the host and execute the command"""
    global successful_hosts, failed_hosts
    retry_attempts = 0

    while retry_attempts < RETRY_COUNT:
        if not check_connection(host_info["hostname"], host_info["port"]):
            logging.warning(f"Host unreachable: {host_info['hostname']}")
            with lock:
                failed_hosts += 1
            return

        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            ssh.connect(
                host_info["hostname"],
                port=host_info["port"],
                username=host_info["username"],
                password=host_info["password"],
                timeout=TIMEOUT,
            )

            stdin, stdout, stderr = ssh.exec_command(command)
            output = stdout.read().decode()
            error = stderr.read().decode()

            if output:
                logging.info(f"Output from {host_info['hostname']}:\n{output}")
            if error:
                logging.error(f"Error from {host_info['hostname']}:\n{error}")

            with lock:
                if error:
                    failed_hosts += 1
                else:
                    successful_hosts += 1

            logging.info(f"Successfully connected to {host_info['hostname']}")
            ssh.close()
            return

        except paramiko.AuthenticationException:
            logging.error(f"Authentication failed: {host_info['hostname']}")
            with lock:
                failed_hosts += 1
            return
        except (paramiko.SSHException, OSError) as e:
            logging.error(f"SSH connection failed: {host_info['hostname']}, error: {e}")
            retry_attempts += 1
            logging.info(f"Retry attempt {retry_attempts}...")
            time.sleep(RETRY_DELAY)
        except Exception as e:
            logging.error(f"Error connecting to {host_info['hostname']}: {e}")
            retry_attempts += 1
            logging.info(f"Retry attempt {retry_attempts}...")
            time.sleep(RETRY_DELAY)

    with lock:
        failed_hosts += 1


def run_commands(command, hosts_file, format_type):
    """Run commands in a thread and update the progress bar"""
    clear_log()  # Clear log and reset counters
    hosts = read_hosts(hosts_file, format_type)
    if not hosts:
        logging.error("No host information found")
        return

    total_hosts = len(hosts)
    logging.info(f"Total hosts to connect: {total_hosts}")
    progress['maximum'] = total_hosts  # Set maximum value for progress bar
    progress['value'] = 0  # Reset progress bar

    with ThreadPoolExecutor() as executor:
        futures = {executor.submit(execute_command, host_info, command): host_info for host_info in hosts}
        for future in futures:
            future.add_done_callback(lambda f: update_progress())

    logging.info(f"Successfully connected hosts: {successful_hosts}")
    logging.info(f"Failed hosts: {failed_hosts}")
    update_output_log()
    messagebox.showinfo("Completed",
                        f"Total hosts: {total_hosts}\nSuccessful: {successful_hosts}\nFailed: {failed_hosts}")


def update_progress():
    """Update the progress bar and output log"""
    with lock:
        progress['value'] += 1  # Increment progress bar
    update_output_log()


def update_output_log():
    """Update log output to the textbox"""
    with open(LOG_FILE, 'r') as file:
        log_content = file.read()
    log_textbox.delete(1.0, tk.END)
    log_textbox.insert(tk.END, log_content)


def open_hosts_file_dialog():
    """Open the file selection dialog"""
    file_path = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
    if file_path:
        hosts_file_var.set(file_path)


def execute_command_action():
    """Execute the user-entered command"""
    command = command_entry.get()
    hosts_file = hosts_file_var.get()
    format_type = format_var.get()
    if not command:
        messagebox.showwarning("Warning", "Please enter a command")
        return
    if not hosts_file:
        messagebox.showwarning("Warning", "Please select a hosts.txt file")
        return
    threading.Thread(target=run_commands, args=(command, hosts_file, format_type)).start()


def clear_log_action():
    """Handle the clear log button click event"""
    clear_log()
    log_textbox.delete(1.0, tk.END)  # Clear log output in the textbox


# Create GUI interface
root = tk.Tk()
root.title("Langmu Security SSH Batch Command Executor")

frame = tk.Frame(root, padx=10, pady=10)
frame.pack()

# Select hosts.txt file
hosts_file_var = tk.StringVar()
format_var = tk.StringVar(value="hostname:port:username:password")  # Default format

label_hosts_file = tk.Label(frame, text="Select hosts.txt file:")
label_hosts_file.grid(row=0, column=0, padx=5, pady=5, sticky="e")

entry_hosts_file = tk.Entry(frame, textvariable=hosts_file_var, width=50)
entry_hosts_file.grid(row=0, column=1, padx=5, pady=5)

btn_select_hosts_file = tk.Button(frame, text="Browse...", command=open_hosts_file_dialog)
btn_select_hosts_file.grid(row=0, column=2, padx=5, pady=5)

# Select hosts file format
label_format = tk.Label(frame, text="Select file format:")
label_format.grid(row=1, column=0, padx=5, pady=5, sticky="e")

format_option_menu = tk.OptionMenu(frame, format_var, "hostname:port:username:password",
                                   "hostname username password port")
format_option_menu.grid(row=1, column=1, padx=5, pady=5, sticky="w")

# Input command
label_command = tk.Label(frame, text="Enter command:")
label_command.grid(row=2, column=0, padx=5, pady=5, sticky="e")

command_entry = tk.Entry(frame, width=50)
command_entry.grid(row=2, column=1, padx=5, pady=5)

btn_execute_command = tk.Button(frame, text="Execute Command", command=execute_command_action)
btn_execute_command.grid(row=2, column=2, padx=5, pady=5)

# Clear log button
btn_clear_log = tk.Button(frame, text="Clear Log", command=clear_log_action)  # Added clear log button
btn_clear_log.grid(row=3, column=2, padx=5, pady=5)

# Progress bar
progress = ttk.Progressbar(frame, orient="horizontal", length=400, mode="determinate")
progress.grid(row=4, column=0, columnspan=3, padx=5, pady=15)

# Log output
log_label = tk.Label(frame, text="Log Output:")
log_label.grid(row=5, column=0, columnspan=3, padx=5, pady=5, sticky="w")

log_textbox = scrolledtext.ScrolledText(frame, width=80, height=20)
log_textbox.grid(row=6, column=0, columnspan=3, padx=5, pady=5)

# Run main loop
root.mainloop()