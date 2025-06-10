import subprocess

def run_script(script_name):
    try:
        print(f"Launching {script_name}...")
        subprocess.run(["python", script_name], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running {script_name}: {e}")

if __name__ == "__main__":
    run_script("entrypoint.py")
    run_script("plate_read.py")