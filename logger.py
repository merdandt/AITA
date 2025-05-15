from colorama import init, Fore, Style

init(autoreset=True)

# --- Define colored logging functions ---
def log_info(message): print(f"{Fore.CYAN}[INFO] {message}{Style.RESET_ALL}")
def log_success(message): print(f"{Fore.GREEN}[SUCCESS] {message}{Style.RESET_ALL}")
def log_warning(message): print(f"{Fore.YELLOW}[WARNING] {message}{Style.RESET_ALL}")
def log_error(message): print(f"{Fore.RED}[ERROR] {message}{Style.RESET_ALL}")
def log_debug(message): print(f"{Fore.MAGENTA}[DEBUG] {message}{Style.RESET_ALL}")
def log_step(step_num, message): print(f"{Fore.BLUE}[STEP {step_num}] {message}{Style.RESET_ALL}")