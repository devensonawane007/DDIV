import shutil
import subprocess

docker_path = shutil.which("docker")
print("Docker in PATH:", bool(docker_path), docker_path)

if docker_path:
    try:
        res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=10)
        print("Docker daemon reachable:", res.returncode == 0)
        if res.returncode != 0:
            print("Docker stderr:", res.stderr.strip()[:200])
    except Exception as e:
        print("Docker check error:", e)
else:
    print("Docker daemon reachable: False (Docker executable not found)")
