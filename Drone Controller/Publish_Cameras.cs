using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System.Net.WebSockets;
using System;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine.Rendering;

[Serializable]
public struct DroneStreamConfig
{
    public string droneId;
    public Camera droneCamera;
    public string serverUrl;
}

public class Publish_Cameras : MonoBehaviour
{
    [Header("Stream Settings")]
    public List<DroneStreamConfig> droneConfigs = new List<DroneStreamConfig>();
    public float framesPerSecond = 10f;
    public Vector2Int resolution = new Vector2Int(640, 480);

    private List<DroneWebSocketClient> clients = new List<DroneWebSocketClient>();

    void Start()
    {
        foreach (var config in droneConfigs)
        {
            if (config.droneCamera == null || string.IsNullOrEmpty(config.serverUrl))
            {
                Debug.LogWarning($"Skipping stream for {config.droneId}: Camera or URL missing.");
                continue;
            }

            var client = new DroneWebSocketClient(config, resolution);
            clients.Add(client);
            StartCoroutine(client.ConnectAndStream(1f / framesPerSecond));
        }
    }

    void OnDestroy()
    {
        foreach (var client in clients)
        {
            client.Disconnect();
        }
    }

    private class DroneWebSocketClient
    {
        private DroneStreamConfig config;
        private Vector2Int res;
        private ClientWebSocket socket;
        private CancellationTokenSource cts;
        private bool isRunning = true;

        private RenderTexture rt;
        private Texture2D tex;
        private float lastCaptureTime = 0;

        public DroneWebSocketClient(DroneStreamConfig config, Vector2Int res)
        {
            this.config = config;
            this.res = res;
            
            // Reusable buffers for performance
            rt = new RenderTexture(res.x, res.y, 24, RenderTextureFormat.ARGB32);
            tex = new Texture2D(res.x, res.y, TextureFormat.RGBA32, false);
        }

        public void Disconnect()
        {
            isRunning = false;
            cts?.Cancel();
            socket?.Dispose();
            if (rt != null) rt.Release();
        }

        public IEnumerator ConnectAndStream(float interval)
        {
            socket = new ClientWebSocket();
            cts = new CancellationTokenSource();

            Uri uri;
            try {
                uri = new Uri(config.serverUrl);
            } catch (Exception e) {
                Debug.LogError($"Invalid URL {config.serverUrl}: {e.Message}");
                yield break;
            }

            Task connectTask = socket.ConnectAsync(uri, cts.Token);
            yield return new WaitUntil(() => connectTask.IsCompleted);

            if (socket.State != WebSocketState.Open)
            {
                Debug.LogError($"Failed to connect to {config.serverUrl} for {config.droneId}");
                yield break;
            }

            Debug.Log($"WebSocket connected for {config.droneId} at {config.serverUrl}");

            while (isRunning && socket.State == WebSocketState.Open)
            {
                if (Time.time >= lastCaptureTime + interval)
                {
                    lastCaptureTime = Time.time;
                    yield return null; 
                    
                    StartCapture();
                }
                yield return null;
            }

            Debug.Log($"WebSocket streaming closed for {config.droneId}");
        }

        private void StartCapture()
        {
            if (config.droneCamera == null || !isRunning) return;

            // Render to texture
            RenderTexture oldRT = config.droneCamera.targetTexture;
            config.droneCamera.targetTexture = rt;
            config.droneCamera.Render();
            config.droneCamera.targetTexture = oldRT;

            // Use AsyncGPUReadback
            AsyncGPUReadback.Request(rt, 0, (request) => {
                if (request.hasError || !isRunning) return;

                var data = request.GetData<byte>().ToArray();
                
                // Process on main thread for texture loading and encoding
                UnityMainThreadDispatcher.Instance().Enqueue(() => {
                    if (tex != null && isRunning) {
                        tex.LoadRawTextureData(data);
                        tex.Apply();
                        byte[] frameData = tex.EncodeToJPG();
                        
                        // Send binary data in background
                        Task.Run(async () => {
                            try {
                                if (socket.State == WebSocketState.Open) {
                                    await socket.SendAsync(new ArraySegment<byte>(frameData), WebSocketMessageType.Binary, true, cts.Token);
                                }
                            } catch (Exception e) {
                                // Socket might have closed
                                System.Console.WriteLine($"Send error for {config.droneId}: {e.Message}");
                            }
                        });
                    }
                });
            });
        }
    }
}
