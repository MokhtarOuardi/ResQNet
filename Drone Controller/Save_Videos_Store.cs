using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System;
using System.IO.Compression;
using System.Diagnostics;
using UnityEngine.Networking;
using UnityEngine.Rendering;
using Debug = UnityEngine.Debug;

[Serializable]
public class DroneReference
{
    public string droneId;
    public Camera droneCamera;
    public GPS gps;
    public Barometer barometer;
    public Battery battery;
    public droneMovementController controller;

    [HideInInspector] public StreamWriter logWriter;
    [HideInInspector] public RenderTexture renderTexture;
    [HideInInspector] public Texture2D texture;

    public void Initialize(string folderPath)
    {
        string logPath = Path.Combine(folderPath, "log.txt");
        logWriter = new StreamWriter(logPath, true);
        logWriter.AutoFlush = true;
        logWriter.WriteLine("FrameNum|Timestamp|GPS_X|GPS_Y|Altitude|BatteryLevel");

        if (Save_Videos_Store.Instance != null) {
            renderTexture = new RenderTexture(Save_Videos_Store.Instance.captureWidth, Save_Videos_Store.Instance.captureHeight, 24, RenderTextureFormat.ARGB32);
            texture = new Texture2D(Save_Videos_Store.Instance.captureWidth, Save_Videos_Store.Instance.captureHeight, TextureFormat.RGBA32, false);
            Debug.Log($"[Save_Videos_Store] Initialized {droneId} with RT {Save_Videos_Store.Instance.captureWidth}x{Save_Videos_Store.Instance.captureHeight}");
        } else {
            Debug.LogError($"[Save_Videos_Store] Failed to initialize {droneId}: Save_Videos_Store.Instance is null!");
        }
    }

    public void Cleanup()
    {
        if (logWriter != null)
        {
            logWriter.Close();
            logWriter = null;
        }
        if (renderTexture != null)
        {
            UnityEngine.Object.Destroy(renderTexture);
            renderTexture = null;
        }
        if (texture != null)
        {
            UnityEngine.Object.Destroy(texture);
            texture = null;
        }
    }
}

public class Save_Videos_Store : MonoBehaviour
{
    public static Save_Videos_Store Instance { get; private set; }

    [Header("Drones to Record")]
    public List<DroneReference> drones = new List<DroneReference>();

    [Header("Recording Settings")]
    public float framesPerSecond = 10f;
    public string folderName = "DroneCaptures";

    [Header("Remote Upload Settings")]
    public string uploadServerUrl = "http://localhost:8080/upload";
    public bool autoUploadOnStop = true;
    public bool deleteLocalAfterUpload = false;

    [Header("Optimization Settings")]
    public int captureWidth = 1280;
    public int captureHeight = 720;
    [Tooltip("Quality of JPG encoding (1-100)")]
    public int jpgQuality = 75;

    private bool isRecording = false;
    private string currentSuffix = "";
    private string currentSessionPath;
    private string masterLogFilePath;
    private int frameCount = 0;
    private float nextCaptureTime = 0f;
    private int _pendingFrames = 0; 
    public int pendingFrames { get => _pendingFrames; } 

    // UnityMainThreadDispatcher is now a standalone script
    void Awake()
    {
        if (Instance == null) Instance = this;
        else Destroy(gameObject);

        // Ensure dispatcher is created on main thread
        UnityMainThreadDispatcher.Instance();
    }

    public void ToggleRecording()
    {
        if (isRecording) StopRecording();
        else StartRecording();
    }

    public void StartRecording(string suffix = "")
    {
        if (isRecording) return;

        isRecording = true;
        currentSuffix = suffix;
        frameCount = 0;
        
        string timestamp = DateTime.Now.ToString("yyyyMMdd_HHmmss");
        string sessionName = timestamp + (string.IsNullOrEmpty(suffix) ? "" : "_" + suffix);
        // Save in project root instead of AppData
        string projectRoot = Path.GetDirectoryName(Application.dataPath);
        currentSessionPath = Path.Combine(projectRoot, folderName, sessionName);
        
        try {
            if (!Directory.Exists(currentSessionPath))
                Directory.CreateDirectory(currentSessionPath);

            foreach (var drone in drones)
            {
                if (string.IsNullOrEmpty(drone.droneId)) {
                    Debug.LogWarning("[Save_Videos_Store] Drone ID is missing! Using 'UnknownDrone'");
                    drone.droneId = "UnknownDrone";
                }
                string droneFolder = Path.Combine(currentSessionPath, drone.droneId);
                Directory.CreateDirectory(droneFolder);
                drone.Initialize(droneFolder);
            }

            masterLogFilePath = Path.Combine(currentSessionPath, "drone_data_log.txt");
            File.WriteAllText(masterLogFilePath, "Timestamp|DroneID|GPS_X|GPS_Y|Altitude|BatteryLevel\n");

            Debug.Log($"Recording started. Saving to: {currentSessionPath}");
        } catch (Exception e) {
            Debug.LogError($"Failed to start recording: {e.Message}");
            isRecording = false;
        }
    }

    public void StopRecording()
    {
        if (!isRecording) return;

        isRecording = false;
        Debug.Log("Recording stopped. Starting post-processing wait...");
        
        // MOVED: drone.Cleanup() now happens after pending frames are finished

        if (autoUploadOnStop)
        {
            StartCoroutine(WaitThenPostProcess());
        }
    }

    private IEnumerator WaitThenPostProcess()
    {
        float startTime = Time.time;
        float timeout = 10f; // Max 10 seconds wait
        
        Debug.Log($"Waiting for {pendingFrames} pending frames to save...");
        while (pendingFrames > 0 && (Time.time - startTime) < timeout)
        {
            yield return new WaitForSeconds(0.1f);
        }

        // NOW we can safely cleanup logs
        foreach (var drone in drones) {
            drone.Cleanup();
        }
        
        if (pendingFrames > 0)
        {
            Debug.LogWarning($"Wait timed out! Proceeding with {pendingFrames} frames still pending.");
        }
        else
        {
            Debug.Log("All frames saved successfully.");
        }
        
        yield return StartCoroutine(PostProcessAndUpload());
    }

    private IEnumerator PostProcessAndUpload()
    {
        // 1. Stitch Videos using FFmpeg (Disabled in Unity, moved to Server side)
        // yield return StartCoroutine(StitchAllVideos());

        // 2. Zip the session folder
        string zipPath = currentSessionPath + ".zip";
        if (File.Exists(zipPath)) File.Delete(zipPath);
        
        Debug.Log($"Zipping directory: {currentSessionPath} to {zipPath}");
        
        // Give OS a moment to release file handles
        yield return new WaitForSeconds(0.5f);

        try {
            ZipFile.CreateFromDirectory(currentSessionPath, zipPath);
            Debug.Log($"Session zipped: {zipPath} ({new FileInfo(zipPath).Length} bytes)");
        } catch (Exception e) {
            Debug.LogError($"Zipping failed: {e.Message}");
            yield break;
        }

        // 3. Upload to server
        yield return StartCoroutine(UploadFile(zipPath));

        if (deleteLocalAfterUpload)
        {
            File.Delete(zipPath);
            // Directory.Delete(currentSessionPath, true); 
        }
    }

    private IEnumerator UploadFile(string filePath)
    {
        if (!File.Exists(filePath))
        {
            Debug.LogError($"Upload failed: File not found at {filePath}");
            yield break;
        }

        byte[] fileData = File.ReadAllBytes(filePath);
        
        List<IMultipartFormSection> formData = new List<IMultipartFormSection>();
        formData.Add(new MultipartFormFileSection("file", fileData, Path.GetFileName(filePath), "application/zip"));

        string uploadUrl = uploadServerUrl;
        if (!string.IsNullOrEmpty(currentSuffix))
        {
            uploadUrl = uploadUrl.TrimEnd('/') + "/" + currentSuffix.ToLower();
        }

        using (UnityWebRequest www = UnityWebRequest.Post(uploadUrl, formData))
        {
            yield return www.SendWebRequest();
            if (www.result != UnityWebRequest.Result.Success)
            {
                Debug.LogError($"Upload failed to {uploadServerUrl}: {www.error}");
            }
            else
            {
                Debug.Log("Upload successful!");
            }
        }
    }

    void Update()
    {
        if (Input.GetKeyDown(KeyCode.R))
        {
            ToggleRecording();
        }

        if (isRecording && Time.time >= nextCaptureTime)
        {
            nextCaptureTime = Time.time + (1f / framesPerSecond);
            CaptureData();
        }
    }

    private void CaptureData()
    {
        string masterTimestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
        
        foreach (var drone in drones)
        {
            if (drone.droneCamera == null) continue;
            
            // Data components
            float gx = 0, gy = 0, alt = 0, batt = 0;
            if (drone.gps != null) {
                var coords = drone.gps.getCoords();
                gx = coords.x; gy = coords.y;
            }
            if (drone.barometer != null) alt = drone.barometer.getHeight() + 15f; // Ground is at -15
            if (drone.battery != null) batt = drone.battery.currentLevel;

            string gpsStr = $"{gx:F6}|{gy:F6}";
            string altStr = alt.ToString("F2");
            string battStr = batt.ToString("F2");
            
            // Log to master file
            string masterEntry = $"{masterTimestamp}|{drone.droneId}|{gpsStr}|{altStr}|{battStr}\n";
            File.AppendAllText(masterLogFilePath, masterEntry);

            // Per-drone capture
            string droneTimestamp = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss.fff");
            float targetAlt = drone.controller != null ? drone.controller.targetY + 15f : -1f;
            string telemetry = $"{droneTimestamp}|{gx:F6}|{gy:F6}|{alt:F2}|{targetAlt:F2}|{batt:F1}";
            
            Debug.Log($"[Save_Videos_Store] Starting capture for {drone.droneId}, frame {frameCount}");
            StartCoroutine(CaptureFrameCoroutine(drone, frameCount, telemetry));
        }

        frameCount++;
    }

    private IEnumerator CaptureFrameCoroutine(DroneReference drone, int currentFrame, string telemetry)
    {
        yield return null;

        if (drone.droneCamera == null || drone.renderTexture == null || drone.texture == null) {
            Debug.LogWarning($"Capture skipped for {drone.droneId}: Missing components (Cam:{drone.droneCamera!=null}, RT:{drone.renderTexture!=null}, Tex:{drone.texture!=null})");
            yield break;
        }

        // Render to the drone's RenderTexture
        RenderTexture oldRT = drone.droneCamera.targetTexture;
        drone.droneCamera.targetTexture = drone.renderTexture;
        drone.droneCamera.Render();
        drone.droneCamera.targetTexture = oldRT;

        // Use AsyncGPUReadback to avoid stalling the main thread (ReadPixels is slow)
        System.Threading.Interlocked.Increment(ref _pendingFrames);
        AsyncGPUReadback.Request(drone.renderTexture, 0, (request) => {
            if (request.hasError) {
                Debug.LogWarning($"GPU Readback failed for drone {drone.droneId}");
                System.Threading.Interlocked.Decrement(ref _pendingFrames);
                return;
            }

            Debug.Log($"[Save_Videos_Store] GPU Readback finished for {drone.droneId}, frame {currentFrame}");

            // Start a task to encode and save in the background
            var data = request.GetData<byte>().ToArray();
            
            System.Threading.Tasks.Task.Run(() => {
                ProcessAndSaveFrame(drone, currentFrame, data, telemetry);
            });
        });
    }

    private void ProcessAndSaveFrame(DroneReference drone, int currentFrame, byte[] rawData, string telemetry)
    {
        try {
            UnityMainThreadDispatcher.Instance().Enqueue(() => {
                if (drone.texture != null) {
                    try {
                        Debug.Log($"[Save_Videos_Store] Encoding frame {currentFrame} for {drone.droneId}");
                        drone.texture.LoadRawTextureData(rawData);
                        drone.texture.Apply();
                        byte[] bytes = drone.texture.EncodeToJPG(jpgQuality);
                        
                        System.Threading.Tasks.Task.Run(() => {
                            try {
                                string fileName = $"frame_{currentFrame}.jpg";
                                string path = Path.Combine(currentSessionPath, drone.droneId, fileName);
                                 File.WriteAllBytes(path, bytes);
                                 Debug.Log($"[Save_Videos_Store] Successfully saved frame {currentFrame} to {path}");
                                 
                                 // Restore missing drone-specific log entry
                                 if (drone.logWriter != null) {
                                     lock (drone.logWriter) {
                                         drone.logWriter.WriteLine($"{currentFrame}|{telemetry}");
                                     }
                                 }
                             } catch (Exception e) {
                                 Debug.LogError($"[Save_Videos_Store] Disk write error for {drone.droneId} frame {currentFrame}: {e.Message}");
                             } finally {
                                 System.Threading.Interlocked.Decrement(ref _pendingFrames);
                             }
                         });
                   } catch (Exception e) {
                        Debug.LogError($"[Save_Videos_Store] Texture processing error for {drone.droneId}: {e.Message}");
                        System.Threading.Interlocked.Decrement(ref _pendingFrames);
                    }
                } else {
                    Debug.LogWarning($"[Save_Videos_Store] Frame dropped for {drone.droneId}: Texture is null");
                    System.Threading.Interlocked.Decrement(ref _pendingFrames);
                }
            });
        } catch (Exception e) {
            Debug.LogError($"[Save_Videos_Store] Dispatcher enqueue error: {e.Message}");
            System.Threading.Interlocked.Decrement(ref _pendingFrames);
        }
    }

    private IEnumerator StitchAllVideos()
    {
        foreach (var drone in drones)
        {
            string droneFolder = Path.Combine(currentSessionPath, drone.droneId);
            string outputVideo = Path.Combine(droneFolder, "drone_video.mp4");
            
            string[] jpgFiles = Directory.GetFiles(droneFolder, "frame_*.jpg");
            Debug.Log($"Found {jpgFiles.Length} JPG frames for {drone.droneId} in {droneFolder}");
            
            if (jpgFiles.Length == 0)
            {
                Debug.LogWarning($"No JPG frames found for {drone.droneId}. Skipping video stitching.");
                continue;
            }

            // Generate FFmpeg command
            // -y: overwrite
            // -framerate: use recording FPS
            // -i frame_%d.jpg: input pattern
            // -c:v libx264 -pix_fmt yuv420p: standard H.264 video
            string ffmpegCmd = $"-y -framerate {framesPerSecond} -i \"frame_%0d.jpg\" -c:v libx264 -pix_fmt yuv420p \"{outputVideo}\"";
            
            Debug.Log($"Stitching video for {drone.droneId} using FFmpeg. Command: ffmpeg {ffmpegCmd}");
            
            yield return StartCoroutine(RunFFmpeg(ffmpegCmd, droneFolder));
        }
    }

    private IEnumerator RunFFmpeg(string args, string workingDir)
    {
        ProcessStartInfo startInfo = new ProcessStartInfo
        {
            FileName = "ffmpeg",
            Arguments = args,
            WorkingDirectory = workingDir,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true
        };

        using (Process process = new Process { StartInfo = startInfo })
        {
            process.Start();
            
            // Read output in background to avoid hanging
            string output = "";
            string error = "";
            process.OutputDataReceived += (s, e) => { if (e.Data != null) output += e.Data + "\n"; };
            process.ErrorDataReceived += (s, e) => { if (e.Data != null) error += e.Data + "\n"; };
            process.BeginOutputReadLine();
            process.BeginErrorReadLine();

            while (!process.HasExited)
            {
                yield return null;
            }

            if (process.ExitCode != 0)
            {
                Debug.LogError($"FFmpeg failed with exit code {process.ExitCode}.\nError: {error}\nOutput: {output}");
            }
            else
            {
                Debug.Log($"FFmpeg finished successfully for {workingDir}");
            }
        }
    }
}

