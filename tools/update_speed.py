import os

# 1. Update app.py to support slower playback speeds: 0.25, 0.5, 1, 2, 5
app_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "app.py")
with open(app_path, "r", encoding="utf-8") as f:
    app_code = f.read()

app_code = app_code.replace('_speed = 5.0', '_speed = 0.5')
app_code = app_code.replace('if value not in (1, 2, 5, 10, 20):',
                            'if value not in (0.25, 0.5, 1, 2, 5, 10, 20):')

with open(app_path, "w", encoding="utf-8") as f:
    f.write(app_code)

# 2. Update index.html to offer slower options: 0.25x, 0.5x, 1x
html_path = os.path.join(os.path.dirname(__file__), "..", "dashboard", "templates", "index.html")
with open(html_path, "r", encoding="utf-8") as f:
    html_code = f.read()

old_speed_options = """          <select id="speed" aria-label="Playback speed">
            <option>1</option>
            <option>2</option>
            <option selected>5</option>
            <option>10</option>
            <option>20</option>
          </select>"""

new_speed_options = """          <select id="speed" aria-label="Playback speed">
            <option value="0.25">0.25 (Very Slow)</option>
            <option value="0.5" selected>0.5 (Smooth / Slow)</option>
            <option value="1">1 (Real Time)</option>
            <option value="2">2 (Fast)</option>
            <option value="5">5 (Fastest)</option>
          </select>"""

if old_speed_options in html_code:
    html_code = html_code.replace(old_speed_options, new_speed_options)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_code)
    print("Updated index.html with slow playback options!")
else:
    print("old_speed_options not found in index.html")

print("Speed settings updated successfully!")
