#!/usr/bin/env python3
"""
audio_player.py - Universal audio playback engine
Handles MP3 playback with multiple fallback methods
"""

import os
import sys
import subprocess
import threading
import time
import shutil
from pathlib import Path
from typing import Optional, Dict
from urllib.parse import urlparse


# =============================================================================
# CONFIGURATION
# =============================================================================

# Headers for streaming audio (important for SermonAudio CloudFront URLs)
STREAM_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.sermonaudio.com/",
    "Accept": "audio/mp3,audio/*;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "identity",
    "Range": "bytes=0-",
}


# =============================================================================
# PLAYER DETECTION
# =============================================================================

def find_ffplay() -> Optional[str]:
    """Find ffplay executable"""
    paths = [
        "ffplay",  # In PATH
        "C:\\ffmpeg\\bin\\ffplay.exe",  # Windows common
        "/usr/local/bin/ffplay",  # Mac Homebrew
        "/opt/homebrew/bin/ffplay",  # Mac M1 Homebrew
        "/usr/bin/ffplay",  # Linux
    ]
    
    for path in paths:
        if shutil.which(path) or os.path.isfile(path):
            return path
    return None


def find_vlc() -> Optional[str]:
    """Find VLC executable"""
    paths = [
        "vlc",  # In PATH
        "C:\\Program Files\\VideoLAN\\VLC\\vlc.exe",  # Windows
        "/Applications/VLC.app/Contents/MacOS/VLC",  # Mac
        "/usr/bin/vlc",  # Linux
    ]
    
    for path in paths:
        if shutil.which(path) or os.path.isfile(path):
            return path
    return None


def find_mpg123() -> Optional[str]:
    """Find mpg123 executable (lightweight CLI player)"""
    return shutil.which("mpg123")


# =============================================================================
# AUDIO PLAYER CLASS
# =============================================================================

class AudioPlayer:
    """Universal audio player with multiple backend support"""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.current_url: Optional[str] = None
        self.is_playing_flag = False
        self.player_type: Optional[str] = None
        self._lock = threading.Lock()
        
        # Detect available players
        self.ffplay_path = find_ffplay()
        self.vlc_path = find_vlc()
        self.mpg123_path = find_mpg123()
        
        # Log available players
        print("\n[Audio Player] Available players:")
        if self.ffplay_path:
            print(f"  ✓ ffplay: {self.ffplay_path}")
        if self.vlc_path:
            print(f"  ✓ VLC: {self.vlc_path}")
        if self.mpg123_path:
            print(f"  ✓ mpg123: {self.mpg123_path}")
        if not any([self.ffplay_path, self.vlc_path, self.mpg123_path]):
            print("  ⚠️  No dedicated players found, will use system default")
    
    def _is_local_file(self, url: str) -> bool:
        """Check if URL is a local file path"""
        return os.path.exists(url) or url.startswith("file://")
    
    def _play_with_ffplay(self, url: str, async_mode: bool = True) -> bool:
        """Play audio using ffplay (best for streaming)"""
        if not self.ffplay_path:
            return False
        
        try:
            # Build ffplay command
            cmd = [
                self.ffplay_path,
                "-nodisp",  # No video window
                "-autoexit",  # Close when done
                "-loglevel", "error",  # Quiet
            ]
            
            # Add streaming headers for online URLs
            if not self._is_local_file(url):
                cmd.extend([
                    "-http_persistent", "1",
                    "-headers", f"Referer: https://www.sermonaudio.com/\r\nUser-Agent: Mozilla/5.0\r\n",
                ])
            
            cmd.append(url)
            
            # Start process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.player_type = "ffplay"
            self.is_playing_flag = True
            
            print(f"  [Audio Player] ▶️  Playing with ffplay (PID: {self.process.pid})")
            
            # Monitor in background if async
            if async_mode:
                threading.Thread(target=self._monitor_process, daemon=True).start()
            else:
                self.process.wait()
                self.is_playing_flag = False
            
            return True
        
        except Exception as e:
            print(f"  [Audio Player] ffplay error: {e}")
            return False
    
    def _play_with_vlc(self, url: str, async_mode: bool = True) -> bool:
        """Play audio using VLC"""
        if not self.vlc_path:
            return False
        
        try:
            cmd = [
                self.vlc_path,
                url,
                "--play-and-exit",
                "--intf", "dummy",  # No GUI
                "--quiet",
            ]
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.player_type = "vlc"
            self.is_playing_flag = True
            
            print(f"  [Audio Player] ▶️  Playing with VLC (PID: {self.process.pid})")
            
            if async_mode:
                threading.Thread(target=self._monitor_process, daemon=True).start()
            else:
                self.process.wait()
                self.is_playing_flag = False
            
            return True
        
        except Exception as e:
            print(f"  [Audio Player] VLC error: {e}")
            return False
    
    def _play_with_mpg123(self, url: str, async_mode: bool = True) -> bool:
        """Play audio using mpg123 (CLI, lightweight)"""
        if not self.mpg123_path:
            return False
        
        try:
            cmd = [self.mpg123_path, "-q", url]  # -q = quiet
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            self.player_type = "mpg123"
            self.is_playing_flag = True
            
            print(f"  [Audio Player] ▶️  Playing with mpg123 (PID: {self.process.pid})")
            
            if async_mode:
                threading.Thread(target=self._monitor_process, daemon=True).start()
            else:
                self.process.wait()
                self.is_playing_flag = False
            
            return True
        
        except Exception as e:
            print(f"  [Audio Player] mpg123 error: {e}")
            return False
    
    def _play_with_system(self, url: str) -> bool:
        """Fallback: Use system default player (browser)"""
        try:
            import webbrowser
            
            print(f"  [Audio Player] ▶️  Opening with system default...")
            
            if self._is_local_file(url):
                url = f"file://{Path(url).absolute()}"
            
            webbrowser.open(url)
            
            self.player_type = "system"
            self.is_playing_flag = True
            
            # Can't monitor system player, so mark as not playing after delay
            def mark_finished():
                time.sleep(5)  # Assume it takes 5s to open
                self.is_playing_flag = False
            
            threading.Thread(target=mark_finished, daemon=True).start()
            
            return True
        
        except Exception as e:
            print(f"  [Audio Player] System player error: {e}")
            return False
    
    def _monitor_process(self):
        """Monitor playback process and update status"""
        if self.process:
            self.process.wait()
            self.is_playing_flag = False
            print(f"  [Audio Player] ⏹️  Playback finished")
    
    def play(self, url: str, async_mode: bool = True) -> bool:
        """
        Play audio from URL or file path.
        
        Args:
            url: MP3 URL or local file path
            async_mode: If True, return immediately; if False, block until done
        
        Returns:
            True if playback started successfully
        """
        with self._lock:
            # Stop any current playback
            if self.is_playing_flag:
                self.stop()
            
            self.current_url = url
            
            print(f"\n[Audio Player] Attempting to play:")
            print(f"  URL: {url[:80]}...")
            
            # Try players in order of preference
            # 1. ffplay (best for streaming)
            if self._play_with_ffplay(url, async_mode):
                return True
            
            # 2. VLC (good all-rounder)
            if self._play_with_vlc(url, async_mode):
                return True
            
            # 3. mpg123 (lightweight CLI)
            if self._play_with_mpg123(url, async_mode):
                return True
            
            # 4. System default (browser)
            if self._play_with_system(url):
                return True
            
            print("  [Audio Player] ❌ All playback methods failed")
            return False
    
    def stop(self):
        """Stop current playback"""
        with self._lock:
            if self.process and self.process.poll() is None:
                print(f"  [Audio Player] ⏹️  Stopping playback...")
                try:
                    self.process.terminate()
                    self.process.wait(timeout=2)
                except:
                    self.process.kill()
                
                self.process = None
            
            self.is_playing_flag = False
            self.current_url = None
            self.player_type = None
    
    def pause(self):
        """Pause playback (not supported by all players)"""
        print("  [Audio Player] ⚠️  Pause not supported, use stop() instead")
    
    def resume(self):
        """Resume playback (not supported)"""
        print("  [Audio Player] ⚠️  Resume not supported, use play() again")
    
    def is_playing(self) -> bool:
        """Check if audio is currently playing"""
        return self.is_playing_flag
    
    def get_status(self) -> Dict[str, any]:
        """Get current player status"""
        return {
            "playing": self.is_playing_flag,
            "url": self.current_url,
            "player": self.player_type,
            "pid": self.process.pid if self.process else None
        }


# =============================================================================
# EXAMPLE USAGE
# =============================================================================

if __name__ == "__main__":
    # Test the audio player
    player = AudioPlayer()
    
    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        # Example URLs
        print("\nNo URL provided. Use: python audio_player.py <url>")
        print("\nExample URLs:")
        print("  Local file: ./hymns/amazing-grace.mp3")
        print("  Online: https://example.com/sermon.mp3")
        sys.exit(1)
    
    print(f"\nTesting playback of: {url}\n")
    
    success = player.play(url, async_mode=True)
    
    if success:
        print("\n✓ Playback started successfully!")
        print("  Press Ctrl+C to stop\n")
        
        try:
            while player.is_playing():
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nStopping...")
            player.stop()
    else:
        print("\n❌ Playback failed")
    
    print("\nDone.")
