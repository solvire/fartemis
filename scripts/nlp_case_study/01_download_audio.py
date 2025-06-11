#!/usr/bin/env python
# -*- coding: utf-8 -*-

import yt_dlp

URLS = ['https://www.youtube.com/watch?v=XH2tF8oB3cw']

ydl_opts = {
    'format': 'bestaudio/best',
    'postprocessors': [{
        'key': 'FFmpegExtractAudio',
        'preferredcodec': 'wav',
        'preferredquality': '192',
    }],
    'outtmpl': 'therapy_session_cbt.%(ext)s',  # Better filename
}

with yt_dlp.YoutubeDL(ydl_opts) as ydl:
    error_code = ydl.download(URLS)