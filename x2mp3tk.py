import os
import json
import subprocess
import re
import time
from tkinter import filedialog, messagebox, Tk, Button, Checkbutton, Text, BooleanVar, StringVar, Frame, Entry, Label
from threading import Thread


sources = []
total_start = 0
total_duration = 0
total_processed = 0


def create_transcoding_subproc(ffmpeg_path, src, dst, bitrate):
    return subprocess.Popen(
        [ffmpeg_path if ffmpeg_path else "ffmpeg", "-y", "-i", src, "-vcodec", "copy", "-acodec", "libmp3lame", "-ab", "{0}k".format(bitrate), dst],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )


def wait_for_transcoding_subproc(src, p, on_subproc_update, on_subproc_exit):
    duration = None
    ok = False
    while True:
        line = p.stdout.readline()
        if not line:
            break
        elif line.startswith("  Duration: "):
            duration = line[12:20]
        elif line.startswith("frame="):
            for s in re.sub(r"= +", "=", line).split(" "):
                k, v = s.split("=")
                if k == "time":
                    on_subproc_update(src, v[0:8], duration)
                    break
        elif line.startswith("video:"):
            p.communicate()
            ok = True
            break
    on_subproc_exit(src, ok)


def get_duration(ffmpeg_path, src):
    ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), "ffprobe{0}".format(os.path.splitext(ffmpeg_path)[1])) if ffmpeg_path else "ffprobe"
    p = subprocess.Popen(
        [ffprobe_path, src],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    out, err = p.communicate()
    pos = out.find("  Duration: ")
    if pos < 0:
        return -1
    duration_h, duration_m, duration_s = out[pos + 12:pos + 20].split(":")
    duration_sec = int(duration_h) * 3600 + int(duration_m) * 60 + int(duration_s)
    return duration_sec


def on_subproc_update(src, t, duration):
    t_h, t_m, t_s = t.split(":")
    t_sec = int(t_h) * 3600 + int(t_m) * 60 + int(t_s)
    duration_h, duration_m, duration_s = duration.split(":")
    duration_sec = int(duration_h) * 3600 + int(duration_m) * 60 + int(duration_s)
    source = next(filter(lambda x: x["src"] == src, sources))
    progress = source["progress"]
    source["progress"] = t_sec * 100.0 / duration_sec
    if int(source["progress"]) != int(progress):
        update_ui()


def progress_info(data):
    if data["progress"] < 1:
        current_eta = "unknown"
    else:
        current_eta = "{0} s".format(int((time.time() - data["start"]) / data["progress"] * (100 - data["progress"])))
    if total_duration < 0:
        total_eta = "unknown"
    else:
        total_progress = (total_processed + data["duration"] * data["progress"] / 100) * 100 / total_duration
        if total_progress < 1:
            total_eta = "unknown"
        else:
            total_eta = "{0} s".format(int((time.time() - total_start) / total_progress * (100 - total_progress)))
    return "{0} % ETA {1} / {2} % ETA {3}".format(int(data["progress"]), current_eta, int(total_progress), total_eta)


def update_ui():
    text.tag_remove("active_line", "1.0", "end")
    text.delete("1.0", "end")
    text.insert("1.0", "\n".join([
        "{0}: {1}".format(
            source["src"] if not source["dst"] else "{0}>{1}".format(source["src"], source["dst"]),
            source["status"] if source["status"] != "processing" else progress_info(source)
        ) for source in sources
    ]))
    active_line = [i for i in range(len(sources)) if sources[i]["status"] == "processing"]
    if active_line:
        active_line = active_line[0] + 1
        text.tag_add("active_line", "{0}.0".format(active_line), "{0}.0".format(active_line + 1))


def on_subproc_exit(src, ok):
    global total_processed

    if not ok:
        messagebox.showerror("Error", "Can not process {0}".format(src))
        exit(1)
    if remove.get():
        try:
            os.remove(src)
        except:
            messagebox.showerror("Error", "Can not remove {0}".format(src))
            exit(1)
    source = next(filter(lambda x: x["src"] == src, sources))
    source["status"] = "done"
    source["end"] = time.time()
    if total_duration > 0:
        total_processed += source["duration"]
    update_ui()


def select_ffmpeg():
    path = filedialog.askopenfilename(title="Select FFMPEG")
    if path:
        ffmpeg_path.set(os.path.normpath(path))
        with open(cfg_path, "w") as f:
            f.write(json.dumps({"ffmpeg_path": path}))


def add_sources():
    paths = filedialog.askopenfilenames(title="Add sources")
    if paths:
        text.insert("end", "\n".join([os.path.normpath(path) for path in paths] + [""]))


def process_in_thread():
    global total_start, total_duration, total_processed

    total_start = time.time()
    total_duration = 0
    total_processed = 0
    for source in sources:
        source["duration"] = get_duration(ffmpeg_path.get(), source["src"])
        if source["duration"] > 0:
            total_duration += source["duration"]
        else:
            total_duration = -1

    for source in sources:
        dst = source["dst"]
        if not dst:
            dir_name = os.path.dirname(source["src"])
            file_name, file_ext = os.path.splitext(os.path.basename(source["src"]))
            dst = os.path.join(dir_name, "{0} mp3{1}".format(file_name, file_ext))
        p = create_transcoding_subproc(ffmpeg_path.get(), source["src"], dst, 192)
        source["start"] = time.time()
        source["status"] = "processing"
        update_ui()
        wait_for_transcoding_subproc(source["src"], p, on_subproc_update, on_subproc_exit)


def process():
    sources.clear()
    for line in text.get("1.0", "end").split("\n"):
        s = line.strip()
        if not s:
            continue
        elems = s.split(">")
        sources.append({"status": "wait", "src": elems[0], "dst": elems[1] if len(elems) > 1 else "", "progress": 0})

    t = Thread(target=process_in_thread)
    t.start()


cfg = {}
cfg_path = "./cfg.json"
if os.path.exists(cfg_path):
    try:
        cfg = json.loads(open(cfg_path).read())
    except:
        pass

root = Tk()
root.title("x2mp3")

root_frame = Frame(root)
root_frame.pack(expand=1, fill="both", padx=8, pady=8)

f = Frame(root_frame)
f.pack(anchor="w")
ffmpeg_path = StringVar()
ffmpeg_path.set(os.path.normpath(cfg.get("ffmpeg_path", "")))
Label(f, text="FFMPEG").pack(side="left")
Frame(f, width=8).pack(side="left")
Entry(f, textvariable=ffmpeg_path, width=100).pack(side="left")
Frame(f, width=8).pack(side="left")
Button(f, text="...", command=select_ffmpeg).pack(side="left")

Frame(root_frame, height=8).pack()

f = Frame(root_frame)
f.pack(anchor="w")
Button(f, text="Add sources", command=add_sources).pack(side="left")
Frame(f, width=8).pack(side="left")
remove = BooleanVar()
remove.set(False)
Checkbutton(f, text="Remove sources after processing", var=remove).pack(side="left")
Frame(f, width=8).pack(side="left")
Button(f, text="Process", command=process).pack(side="left")

Frame(root_frame, height=8).pack()

info = Label(root_frame, text="Note: you can specify the path to the destination file as follows: src.ext>dst.ext (src mp3.ext will be used if not specified)").pack(anchor="w")

Frame(root_frame, height=8).pack()

text = Text(root_frame)
text.pack(expand=1, fill="both")
text.tag_configure("active_line", foreground="red")

root.mainloop()
