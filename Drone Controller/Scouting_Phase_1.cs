using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Threading;
using System.IO;
using System.Text;

[System.Serializable]
public class CoordData { public float x; public float y; }
[System.Serializable]
public class Phase2ZoneData { public float minX, maxX, minZ, maxZ; }
[System.Serializable]
public class MissionData { public CoordData[] corners; public Phase2ZoneData[] phase2_zones; }

public class Scouting_Phase_1 : MonoBehaviour
{
    public enum MissionState
    {
        IDLE,
        P1_TRANSIT_TO_AREA,
        P1_SCOUTING,
        P1_TRANSIT_TO_CENTER,
        P2_SCOUTING,
        P2_TRANSIT_TO_CENTER,
        RETURNING_HOME,
        COMPLETED
    }

    [Header("Mission Configuration")]
    public Vector2[] areaCorners = new Vector2[4];
    public float arrivalThreshold = 3f;
    public bool startOnRun = false;
    public KeyCode startKey = KeyCode.S;
    public bool enableRecording = false;

    [Header("HTTP Coordination")]
    public int httpPort = 5000;
    private TcpListener tcpListener;
    private Thread httpThread;
    private MissionData pendingHttpMission;
    private Phase2ZoneData[] receivedPhase2Zones;
    private bool httpTriggeredPhase2 = false; 
    private readonly object httpLock = new object();

    [Header("Phase 1 - Lane Sweep")]
    public float phase1Altitude = 20f;
    public int phase1WaypointsPerLane = 5;

    [Header("Phase 2 - Quadrant Sweep")]
    public float phase2Altitude = 8f;
    public int phase2SweepRows = 4;

    [Header("Path Following")]
    [Tooltip("Speed at which the singlePoint moves along paths (m/s)")]
    public float targetMoveSpeed = 5f;
    [Tooltip("Seconds to hover at each waypoint before advancing")]
    public float waypointHoverTime = 1f;
    [Tooltip("Extra seconds to wait at phase transition points for all drones")]
    public float transitWaitTime = 3f;

    [Header("Terrain Adaptation")]
    public float raycastOriginHeight = 200f;
    public LayerMask groundLayer = -1;

    [Header("Autonomous Navigation & Mapping")]
    public float scanRadius = 15f;
    public bool useAStar = true;
    [Tooltip("Extra vertical clearance added to all waypoints for safety")]
    public float safetyBuffer = 2f;

    [Header("Trajectory Visualization")]
    public bool drawTrajectories = true;
    public float trajectoryLineWidth = 0.15f;

    [Header("Status")]
    public MissionState currentState = MissionState.IDLE;

    private Vector3 areaCenter;
    private Vector3[] homePositions = new Vector3[4];

    private List<Vector3>[] droneWaypoints = new List<Vector3>[4];
    private int[] currentWaypointIndices = new int[4];
    private bool[] droneFinished = new bool[4];
    private float[] hoverTimers = new float[4];
    private bool waitingForDrones = false;
    private bool waitingForPhase2 = false;
    private float transitTimer = 0f;

    // A* Path following
    private List<Vector3>[] activeAStarPaths = new List<Vector3>[4];
    private int[] aStarPathIndices = new int[4];

    // Trajectory tracking
    private List<Vector3>[] droneTrajectories = new List<Vector3>[4];
    private LineRenderer[] trajectoryRenderers = new LineRenderer[4];
    private Color[] droneColors = { Color.red, Color.blue, Color.green, Color.magenta };

    // In-game visualizations
    private LineRenderer areaBoundaryRenderer;
    private LineRenderer[] missionPathRenderers = new LineRenderer[4];
    private LineRenderer[] aStarPathRenderers = new LineRenderer[4];
    private GameObject[] startMarkers = new GameObject[4];
    private GameObject[] targetMarkers = new GameObject[4];
    private List<GameObject>[] lookaheadMarkers = new List<GameObject>[4];

    private void Awake()
    {
        // 1. Initialize all arrays and lists immediately
        var organizer = Swarm_Drone_Organizer.Instance;
        for (int i = 0; i < 4; i++)
        {
            droneTrajectories[i] = new List<Vector3>();
            droneWaypoints[i] = new List<Vector3>();
            lookaheadMarkers[i] = new List<GameObject>();
            _pendingLaneWaypoints[i] = new List<Vector3>();

            // Store original home positions
            if (organizer != null && organizer.swarmDrones.Count > i && organizer.swarmDrones[i].singlePoint != null)
                homePositions[i] = organizer.swarmDrones[i].singlePoint.position;
            else
            {
                // Fallback to user provided defaults if not available at Awake
                if (i == 0) homePositions[0] = new Vector3(67.42f, 213.97f, -497.88f);
                if (i == 1) homePositions[1] = new Vector3(131.30f, 223.15f, -543.22f);
                if (i == 2) homePositions[2] = new Vector3(160.55f, 228.91f, -561.08f);
                if (i == 3) homePositions[3] = new Vector3(39.54f, 245.37f, -672.06f);
            }
        }

        // 2. Setup Server
        httpPort = 5000;
        Application.runInBackground = true;
        
        // 3. Initialize Renderers EARLY
        InitTrajectoryRenderers();
        StartHttpServer();
    }

    void Start()
    {
        if (startOnRun) StartMission();
    }

    void OnDestroy()
    {
        StopHttpServer();
    }

    private void StartHttpServer()
    {
        try
        {
            tcpListener = new TcpListener(IPAddress.Loopback, httpPort);
            tcpListener.Start();
            httpThread = new Thread(ListenForHttpRequests);
            httpThread.IsBackground = true;
            httpThread.Start();
            Debug.Log($"[Scouting] TCP Listener started on {IPAddress.Loopback}:{httpPort}");
        }
        catch (System.Exception e)
        {
            Debug.LogError($"[Scouting] Failed to start TCP server: {e.Message}");
        }
    }

    private void StopHttpServer()
    {
        if (tcpListener != null)
        {
            tcpListener.Stop();
        }
        if (httpThread != null && httpThread.IsAlive)
            httpThread.Abort();
    }

    private void ListenForHttpRequests()
    {
        while (true)
        {
            TcpClient client = null;
            try
            {
                client = tcpListener.AcceptTcpClient();
                Debug.Log($"[Scouting] TCP Connection accepted from {client.Client.RemoteEndPoint}");

                using (NetworkStream stream = client.GetStream())
                using (StreamReader reader = new StreamReader(stream))
                {
                    string firstLine = reader.ReadLine();
                    if (string.IsNullOrEmpty(firstLine)) { client.Close(); continue; }

                    int contentLength = 0;
                    string headerLine;
                    while (!string.IsNullOrEmpty(headerLine = reader.ReadLine()))
                    {
                        if (headerLine.StartsWith("Content-Length:", System.StringComparison.OrdinalIgnoreCase))
                        {
                            int.TryParse(headerLine.Substring(15).Trim(), out contentLength);
                        }
                    }

                    if (contentLength > 0)
                    {
                        char[] bodyBuffer = new char[contentLength];
                        int bytesRead = reader.ReadBlock(bodyBuffer, 0, contentLength);
                        string json = new string(bodyBuffer, 0, bytesRead);
                        
                        Debug.Log($"[Scouting] TCP-HTTP Received ({bytesRead} bytes): {json}");
                        
                        MissionData data = JsonUtility.FromJson<MissionData>(json);
                        if (data != null)
                        {
                            lock (httpLock) { pendingHttpMission = data; }
                        }
                    }
                    else
                    {
                        Debug.LogWarning("[Scouting] TCP-HTTP request received but no Content-Length found.");
                    }

                    // Simple HTTP Response
                    byte[] response = Encoding.UTF8.GetBytes("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK");
                    stream.Write(response, 0, response.Length);
                }
            }
            catch (System.Exception e) 
            { 
                if (tcpListener != null) Debug.LogWarning($"[Scouting] TCP Listener error or closed: {e.Message}");
            }
            finally
            {
                if (client != null) client.Close();
            }
        }
    }

    [ContextMenu("Force Update Visuals")]
    public void ManualUpdateVisuals()
    {
        UpdateInGameVisuals();
        if (areaBoundaryRenderer != null && areaCorners != null && areaCorners.Length == 4)
        {
            areaBoundaryRenderer.positionCount = 4;
            for (int i = 0; i < 4; i++)
                areaBoundaryRenderer.SetPosition(i, new Vector3(areaCorners[i].x, phase1Altitude, areaCorners[i].y));
        }
    }

    private Material _cachedBaseMaterial;
    private Material GetRobustMaterial(Color color)
    {
        if (_cachedBaseMaterial == null)
        {
            // Use SpriteRenderer's default material - it's robust, supports transparency and vertex colors
            GameObject temp = new GameObject("TempSprite");
            SpriteRenderer sr = temp.AddComponent<SpriteRenderer>();
            if (sr.sharedMaterial != null)
            {
                _cachedBaseMaterial = Instantiate(sr.sharedMaterial);
            }
            else
            {
                // Fallback to internal-colored if sprite fails
                _cachedBaseMaterial = new Material(Shader.Find("Hidden/Internal-Colored"));
            }
            Destroy(temp);
        }

        Material m = Instantiate(_cachedBaseMaterial);
        m.color = color;
        // Also set properties explicitly just in case
        if (m.HasProperty("_Color")) m.SetColor("_Color", color);
        if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", color);
        
        m.renderQueue = 3000;
        return m;
    }

    private void InitTrajectoryRenderers()
    {
        // 1. Area Boundary Renderer
        GameObject areaObj = new GameObject("Area_Boundary_Renderer");
        areaObj.transform.SetParent(transform);
        areaBoundaryRenderer = areaObj.AddComponent<LineRenderer>();
        ConfigureLineRenderer(areaBoundaryRenderer, Color.yellow, 0.3f, true);

        for (int i = 0; i < 4; i++)
        {
            // 2. Trajectory Renderer (History)
            GameObject trajObj = new GameObject($"Trajectory_Drone_{i}");
            trajObj.transform.SetParent(transform);
            trajectoryRenderers[i] = trajObj.AddComponent<LineRenderer>();
            ConfigureLineRenderer(trajectoryRenderers[i], droneColors[i], trajectoryLineWidth);

            // 3. Mission Path Renderer (Future Serpantine)
            GameObject missionObj = new GameObject($"MissionPath_Drone_{i}");
            missionObj.transform.SetParent(transform);
            missionPathRenderers[i] = missionObj.AddComponent<LineRenderer>();
            ConfigureLineRenderer(missionPathRenderers[i], droneColors[i], 0.35f);

            // 4. A* Path Renderer (Immediate segment)
            GameObject astarObj = new GameObject($"AStarPath_Drone_{i}");
            astarObj.transform.SetParent(transform);
            aStarPathRenderers[i] = astarObj.AddComponent<LineRenderer>();
            ConfigureLineRenderer(aStarPathRenderers[i], droneColors[i], 0.6f);

            // 5. Start/Target Markers
            startMarkers[i] = GameObject.CreatePrimitive(PrimitiveType.Cube);
            startMarkers[i].name = $"StartMarker_Drone_{i}";
            startMarkers[i].transform.localScale = Vector3.one * 1.2f;
            startMarkers[i].transform.SetParent(transform);
            startMarkers[i].GetComponent<Renderer>().material = GetRobustMaterial(droneColors[i]);
            Destroy(startMarkers[i].GetComponent<BoxCollider>());

            targetMarkers[i] = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            targetMarkers[i].name = $"TargetMarker_Drone_{i}";
            targetMarkers[i].transform.localScale = Vector3.one * 0.8f;
            targetMarkers[i].transform.SetParent(transform);
            targetMarkers[i].GetComponent<Renderer>().material = GetRobustMaterial(Color.white);
            Destroy(targetMarkers[i].GetComponent<SphereCollider>());

            // 6. Lookahead Markers
            lookaheadMarkers[i] = new List<GameObject>();
            for (int k = 0; k < 10; k++)
            {
                GameObject lookahead = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                lookahead.name = $"WpMarker_{i}_{k}";
                lookahead.transform.localScale = Vector3.one * 0.3f;
                lookahead.transform.SetParent(transform);
                lookahead.GetComponent<Renderer>().material = GetRobustMaterial(droneColors[i]);
                Destroy(lookahead.GetComponent<SphereCollider>());
                lookahead.SetActive(false);
                lookaheadMarkers[i].Add(lookahead);
            }
        }
    }

    private void ConfigureLineRenderer(LineRenderer lr, Color color, float width, bool loop = false)
    {
        lr.startWidth = width;
        lr.endWidth = width;
        lr.material = GetRobustMaterial(color);
        lr.startColor = color;
        lr.endColor = color;
        lr.positionCount = 0;
        lr.loop = loop;
    }

    [ContextMenu("Start Mission")]
    public void StartMission()
    {
        if (areaCorners.Length != 4)
        {
            Debug.LogError("[Scouting] Area Corners must have 4 points!");
            return;
        }

        float avgX = areaCorners.Average(c => c.x);
        float avgZ = areaCorners.Average(c => c.y);
        // Fixed altitude for Phase 1
        areaCenter = new Vector3(avgX, phase1Altitude, avgZ);
        // Initialize Mapping Grid
        if (Scouting_Grid_Mapper.Instance != null)
            Scouting_Grid_Mapper.Instance.InitializeGrid(areaCorners);

        // Clear trajectories safely
        for (int i = 0; i < 4; i++)
        {
            if (droneTrajectories != null && droneTrajectories[i] != null)
                droneTrajectories[i].Clear();
            
            if (trajectoryRenderers != null && trajectoryRenderers[i] != null)
                trajectoryRenderers[i].positionCount = 0;
        }

        // Safety check for drones
        if (Swarm_Drone_Organizer.Instance == null || Swarm_Drone_Organizer.Instance.swarmDrones == null)
        {
            Debug.LogError("[Scouting] Swarm_Drone_Organizer not ready! Aborting StartMission.");
            currentState = MissionState.IDLE;
            return;
        }

        // Build transit path: just the formation point at area center
        var organizer = Swarm_Drone_Organizer.Instance;
        CalculateLanes(); // Pre-calculate lanes for later
        for (int i = 0; i < 4; i++)
        {
            // Store lane waypoints temporarily
            var laneWaypoints = droneWaypoints[i];
            // Transit path: individual formation position with FIXED altitude
            droneWaypoints[i] = new List<Vector3>();
            Vector3 formationPos = areaCenter + organizer.swarmDrones[i].localOffset;
            Vector3 transitPoint = new Vector3(formationPos.x, phase1Altitude, formationPos.z);
            droneWaypoints[i].Add(transitPoint);
            // Stash lanes for after arrival
            _pendingLaneWaypoints[i] = laneWaypoints;
        }

        InitSmoothMovement();

        // Update Area Boundary visualization
        if (areaBoundaryRenderer != null)
        {
            areaBoundaryRenderer.positionCount = 4;
            for (int i = 0; i < 4; i++)
            {
                areaBoundaryRenderer.SetPosition(i, new Vector3(areaCorners[i].x, phase1Altitude, areaCorners[i].y));
            }
        }

        currentState = MissionState.P1_TRANSIT_TO_AREA;
        Debug.Log($"[Scouting] Mission Started. Moving to area formation.");
    }

    // Stashed lane waypoints loaded after transit
    private List<Vector3>[] _pendingLaneWaypoints = new List<Vector3>[4];

    void Update()
    {
        // 1. Check for HTTP mission data
        MissionData newData = null;
        lock (httpLock)
        {
            if (pendingHttpMission != null)
            {
                newData = pendingHttpMission;
                pendingHttpMission = null;
            }
        }

        if (newData != null)
        {
            if (newData.corners != null && newData.corners.Length == 4)
            {
                Debug.Log("[Scouting] Remote Phase 1 data parsed successfully.");
                for (int i = 0; i < 4; i++)
                {
                    areaCorners[i] = new Vector2(newData.corners[i].x, newData.corners[i].y);
                }
                if (currentState == MissionState.IDLE) StartMission();
            }

            if (newData.phase2_zones != null)
            {
                Debug.Log($"[Scouting] Remote Phase 2 data received: {newData.phase2_zones.Length} zones.");
                if (newData.phase2_zones.Length == 4)
                {
                    receivedPhase2Zones = newData.phase2_zones;
                    httpTriggeredPhase2 = true;
                    Debug.Log("[Scouting] Phase 2 trigger LATCHED.");
                }
                else
                {
                    Debug.LogWarning($"[Scouting] Received {newData.phase2_zones.Length} Phase 2 zones, but expected 4.");
                }
            }
        }

        // 2. Manual Start Trigger (Phase 1)
        if (currentState == MissionState.IDLE && Input.GetKeyDown(startKey))
        {
            StartMission();
        }

        if (drawTrajectories && currentState != MissionState.IDLE && currentState != MissionState.COMPLETED)
            RecordTrajectories();

        // Always update indicators if mission is active, regardless of recording setting
        if (currentState != MissionState.IDLE && currentState != MissionState.COMPLETED)
            UpdateInGameVisuals();

        switch (currentState)
        {
            case MissionState.P1_TRANSIT_TO_AREA:
                SmoothMoveDrones();
                if (droneFinished.All(f => f))
                {
                    if (WaitForAllDronesAtTargets())
                    {
                        // Load the stashed lane waypoints
                        for (int i = 0; i < 4; i++)
                            droneWaypoints[i] = _pendingLaneWaypoints[i];
                        InitSmoothMovement();
                        if (enableRecording && Save_Videos_Store.Instance != null)
                            Save_Videos_Store.Instance.StartRecording("P1");
                        currentState = MissionState.P1_SCOUTING;
                        Debug.Log("[Phase1] All drones settled. Scouting lanes...");
                    }
                }
                break;

            case MissionState.P1_SCOUTING:
                SmoothMoveDrones();

                // Real-time Mapping
                if (Scouting_Grid_Mapper.Instance != null)
                {
                    for (int i = 0; i < 4; i++)
                    {
                        var drone = Swarm_Drone_Organizer.Instance.swarmDrones[i];
                        if (drone.controller != null)
                            Scouting_Grid_Mapper.Instance.UpdateMap(drone.controller.transform.position, scanRadius);
                    }
                }

                if (droneFinished.All(f => f))
                {
                    if (enableRecording && Save_Videos_Store.Instance != null)
                        Save_Videos_Store.Instance.StopRecording();
                    BuildReturnPath(areaCenter, phase1Altitude, true); // Use corners for P1->P2 transition
                    currentState = MissionState.P1_TRANSIT_TO_CENTER;
                    Debug.Log("[Phase1] Lanes done. Moving to corner standoff for phase 2...");
                }
                break;

            case MissionState.P1_TRANSIT_TO_CENTER:
                SmoothMoveDrones();
                if (droneFinished.All(f => f))
                {
                    if (!waitingForPhase2)
                    {
                        if (WaitForAllDronesAtTargets())
                        {
                            Debug.Log("[Phase1] Mission Complete. Press 'S' to begin Phase 2 (Low Scouting)...");
                            waitingForPhase2 = true;
                        }
                    }
                    else
                    {
                        if (Input.GetKeyDown(startKey) || httpTriggeredPhase2)
                        {
                            httpTriggeredPhase2 = false;
                            waitingForPhase2 = false;
                            Debug.Log("[Phase2] Initializing...");
                            CalculateQuadrants();
                            InitSmoothMovement();
                            currentState = MissionState.P2_SCOUTING;
                            if (enableRecording && Save_Videos_Store.Instance != null)
                                Save_Videos_Store.Instance.StartRecording("P2");
                            Debug.Log("[Phase2] Low sweep started.");
                        }
                    }
                }
                break;

            case MissionState.P2_SCOUTING:
                SmoothMoveDrones();
                if (droneFinished.All(f => f))
                {
                    if (enableRecording && Save_Videos_Store.Instance != null)
                        Save_Videos_Store.Instance.StopRecording();
                    // Final return to center with drone offsets
                    BuildReturnPath(areaCenter, phase2Altitude, false);
                    currentState = MissionState.P2_TRANSIT_TO_CENTER;
                    Debug.Log("[Phase2] Sweeps done. Returning to center formation...");
                }
                break;

            case MissionState.P2_TRANSIT_TO_CENTER:
                SmoothMoveDrones();
                if (droneFinished.All(f => f))
                {
                    if (WaitForAllDronesAtTargets())
                    {
                        BuildHomePath();
                        currentState = MissionState.RETURNING_HOME;
                        Debug.Log("[Scouting] Returning to base coordinates...");
                    }
                }
                break;

            case MissionState.RETURNING_HOME:
                SmoothMoveDrones();
                if (droneFinished.All(f => f))
                {
                    if (WaitForAllDronesAtTargets())
                    {
                        currentState = MissionState.IDLE;
                        Debug.Log("[Scouting] Mission Loop complete. System IDLE and ready for new Phase 1.");
                        // Clean up state
                        for (int i = 0; i < 4; i++)
                        {
                            _pendingLaneWaypoints[i].Clear();
                            currentWaypointIndices[i] = 0;
                        }
                    }
                }
                break;
        }
    }

    private void BuildHomePath()
    {
        for (int i = 0; i < 4; i++)
        {
            droneWaypoints[i] = new List<Vector3> { homePositions[i] };
            currentWaypointIndices[i] = 0;
            droneFinished[i] = false;
            hoverTimers[i] = 0f;
        }
    }

    private void UpdateInGameVisuals()
    {
        for (int i = 0; i < 4; i++)
        {
            List<Vector3> visualPath = new List<Vector3>();
            var drone = Swarm_Drone_Organizer.Instance.swarmDrones[i];

            // 1. Calculate displayY (Standardized for the current active phase)
            // Use phase1Altitude for everyone until we officially move to Phase 2
            float displayY = (currentState < MissionState.P2_SCOUTING) ? phase1Altitude : phase2Altitude;

            // 2. Control Visibility (Hide lanes/dots during transit)
            bool showLanes = (currentState == MissionState.P1_SCOUTING || currentState == MissionState.P2_SCOUTING);

            // 3. Select Source Waypoints (Only if lanes should be shown)
            List<Vector3> sourceWaypoints = (showLanes) ? (droneWaypoints[i] ?? new List<Vector3>()) : new List<Vector3>();

            // Apply Opacity to both Material and Vertex colors
            Color missionColor = droneColors[i];
            missionColor.a = 0.4f; 
            if (missionPathRenderers[i] != null)
            {
                missionPathRenderers[i].material.color = missionColor; // Set Material Color
                missionPathRenderers[i].startColor = missionColor;
                missionPathRenderers[i].endColor = missionColor;
            }
            if (showLanes && sourceWaypoints.Count > 0)
            {
                // Full path lines (Matching "outside perimeter" method)
                foreach (var wp in sourceWaypoints)
                {
                    visualPath.Add(new Vector3(wp.x, displayY, wp.z));
                }

                // Update Mission Start Cube
                if (startMarkers[i] != null)
                {
                    startMarkers[i].SetActive(true);
                    startMarkers[i].transform.position = new Vector3(sourceWaypoints[0].x, displayY, sourceWaypoints[0].z);
                }

                // Update Waypoint Dots
                int startIdx = currentWaypointIndices[i];
                for (int k = 0; k < 10; k++)
                {
                    int wpIdx = startIdx + 1 + k;
                    if (wpIdx < sourceWaypoints.Count)
                    {
                        lookaheadMarkers[i][k].SetActive(true);
                        Vector3 wp = sourceWaypoints[wpIdx];
                        lookaheadMarkers[i][k].transform.position = new Vector3(wp.x, displayY, wp.z);
                    }
                    else
                    {
                        lookaheadMarkers[i][k].SetActive(false);
                    }
                }
            }
            else
            {
                // If in transit, hide lanes and starting cubes. 
                if (startMarkers[i] != null) startMarkers[i].SetActive(false);
                foreach (var m in lookaheadMarkers[i]) m.SetActive(false);
                // LineRenderer will be cleared by the visualPath being empty
            }

            // 4. Target Marker (the "arrival sphere" or current active goal)
            if (droneWaypoints[i] != null && !droneFinished[i])
            {
                targetMarkers[i].SetActive(true);
                Vector3 targetPos;
                if (useAStar && currentState == MissionState.P2_SCOUTING && activeAStarPaths[i] != null && aStarPathIndices[i] < activeAStarPaths[i].Count)
                    targetPos = activeAStarPaths[i][aStarPathIndices[i]];
                else
                    targetPos = droneWaypoints[i][currentWaypointIndices[i]];

                targetMarkers[i].transform.position = targetPos;
                targetMarkers[i].GetComponent<Renderer>().material.color = waitingForDrones ? Color.red : Color.white;
            }
            else
            {
                targetMarkers[i].SetActive(false);
            }

            // 3. Update Mission Path Renderer
            if (missionPathRenderers[i] != null)
            {
                missionPathRenderers[i].positionCount = visualPath.Count;
                missionPathRenderers[i].SetPositions(visualPath.ToArray());
            }

            // 4. Update Active A* Path Renderer
            if (aStarPathRenderers[i] != null)
            {
                if (activeAStarPaths[i] != null && aStarPathIndices[i] < activeAStarPaths[i].Count)
                {
                    int currentId = aStarPathIndices[i];
                    int remainingAStar = activeAStarPaths[i].Count - currentId;

                    aStarPathRenderers[i].positionCount = remainingAStar + 1;
                    aStarPathRenderers[i].SetPosition(0, drone.singlePoint != null ? drone.singlePoint.position : visualPath.Count > 0 ? visualPath[0] : Vector3.zero);

                    for (int j = 0; j < remainingAStar; j++)
                    {
                        aStarPathRenderers[i].SetPosition(j + 1, activeAStarPaths[i][currentId + j]);
                    }
                }
                else
                {
                    aStarPathRenderers[i].positionCount = 0;
                }
            }
        }
    }

    // ==================== Unified Smooth Movement ====================

    private void InitSmoothMovement()
    {
        for (int i = 0; i < 4; i++)
        {
            currentWaypointIndices[i] = 0;
            droneFinished[i] = false;
            hoverTimers[i] = 0f;
            activeAStarPaths[i] = null;
            aStarPathIndices[i] = 0;
        }
        waitingForDrones = false;
        transitTimer = 0f;
    }

    private void SmoothMoveDrones()
    {
        for (int i = 0; i < 4; i++)
        {
            if (droneFinished[i]) continue;

            var drone = Swarm_Drone_Organizer.Instance.swarmDrones[i];
            if (drone.singlePoint == null) continue;

            if (hoverTimers[i] > 0f)
            {
                hoverTimers[i] -= Time.deltaTime;
                continue;
            }

            Vector3 targetPosition;
            bool isAtFinalWaypoint = false;

            // Handle A* Path Following
            if (useAStar && currentState == MissionState.P2_SCOUTING && Scouting_Grid_Mapper.Instance != null)
            {
                if (activeAStarPaths[i] == null)
                {
                    // Generate new A* path to the current mission waypoint
                    Vector3 start = drone.singlePoint.position;
                    Vector3 end = droneWaypoints[i][currentWaypointIndices[i]];
                    activeAStarPaths[i] = Scouting_Grid_Mapper.Instance.FindPath(start, end, phase2Altitude);
                    aStarPathIndices[i] = 0;

                    if (activeAStarPaths[i] == null)
                    {
                        Debug.LogWarning($"[Scouting] Drone {i} could not find A* path. Falling back to direct move.");
                        targetPosition = end;
                    }
                    else
                    {
                        targetPosition = activeAStarPaths[i][0];
                    }
                }
                else
                {
                    targetPosition = activeAStarPaths[i][aStarPathIndices[i]];
                }
            }
            else
            {
                targetPosition = droneWaypoints[i][currentWaypointIndices[i]];
            }

            Vector3 current = drone.singlePoint.position;
            drone.singlePoint.position = Vector3.MoveTowards(current, targetPosition, targetMoveSpeed * Time.deltaTime);

            if (Vector3.Distance(drone.singlePoint.position, targetPosition) < 0.5f)
            {
                // Advance A* or Waypoint
                if (useAStar && currentState == MissionState.P2_SCOUTING && activeAStarPaths[i] != null)
                {
                    aStarPathIndices[i]++;
                    if (aStarPathIndices[i] >= activeAStarPaths[i].Count)
                    {
                        activeAStarPaths[i] = null; // Finished this A* segment
                        isAtFinalWaypoint = true;
                    }
                }
                else
                {
                    isAtFinalWaypoint = true;
                }

                if (isAtFinalWaypoint)
                {
                    currentWaypointIndices[i]++;
                    if (currentWaypointIndices[i] >= droneWaypoints[i].Count)
                    {
                        droneFinished[i] = true;
                    }
                    else
                    {
                        hoverTimers[i] = waypointHoverTime;
                    }
                }
            }
        }
    }

    /// <summary>
    /// Waits for all physical drones to arrive near their respective current target waypoints, then waits transitWaitTime.
    /// Returns true when the wait is complete.
    /// </summary>
    private bool WaitForAllDronesAtTargets()
    {
        if (!waitingForDrones)
        {
            // Use generous tolerance - PID drones oscillate
            float tolerance = arrivalThreshold * 3f;
            bool allArrived = true;
            for (int i = 0; i < 4; i++)
            {
                var drone = Swarm_Drone_Organizer.Instance.swarmDrones[i];
                if (drone.controller == null) continue;

                // Check against the LAST waypoint in their current list (the transit target)
                if (droneWaypoints[i] == null || droneWaypoints[i].Count == 0) continue;
                Vector3 target = droneWaypoints[i].Last();

                float dist = Vector3.Distance(drone.controller.transform.position, target);
                if (dist > tolerance)
                {
                    allArrived = false;
                    break;
                }
            }
            if (allArrived)
            {
                waitingForDrones = true;
                transitTimer = transitWaitTime;
                Debug.Log("[Scouting] All drones reached standoff targets. Waiting to settle...");
            }
            return false;
        }
        else
        {
            transitTimer -= Time.deltaTime;
            if (transitTimer <= 0f)
            {
                waitingForDrones = false;
                return true;
            }
            return false;
        }
    }

    private bool AllDronesReachedIndex(int index)
    {
        for (int i = 0; i < 4; i++)
        {
            if (currentWaypointIndices[i] <= index) return false;
        }
        return true;
    }

    private void BuildReturnPath(Vector3 center, float altitude, bool useCorners = true)
    {
        var organizer = Swarm_Drone_Organizer.Instance;
        bool useFixedAlt = Mathf.Approximately(altitude, phase1Altitude);

        // Define corners of the Search Area for wide standoff
        float minX = areaCorners.Min(c => c.x);
        float maxX = areaCorners.Max(c => c.x);
        float minZ = areaCorners.Min(c => c.y);
        float maxZ = areaCorners.Max(c => c.y);

        Vector3[] corners = {
            new Vector3(minX, altitude, minZ),
            new Vector3(maxX, altitude, minZ),
            new Vector3(minX, altitude, maxZ),
            new Vector3(maxX, altitude, maxZ)
        };

        // Fallback formation for centered return (small 4m square)
        Vector3[] centeredFormation = {
            center + new Vector3(-2, 0, -2),
            center + new Vector3(2, 0, -2),
            center + new Vector3(-2, 0, 2),
            center + new Vector3(2, 0, 2)
        };

        for (int i = 0; i < 4; i++)
        {
            droneWaypoints[i] = new List<Vector3>();

            // Choose between wide standoff or centered offsets
            Vector3 standoffPos = useCorners ? corners[i] : centeredFormation[i];

            if (useFixedAlt)
            {
                droneWaypoints[i].Add(new Vector3(standoffPos.x, altitude, standoffPos.z));
            }
            else
            {
                float droneGroundH = RobustSampleGroundHeight(standoffPos.x, standoffPos.z);
                Vector3 returnPoint = EnsureClearance(new Vector3(standoffPos.x, droneGroundH + altitude, standoffPos.z));
                droneWaypoints[i].Add(returnPoint);
            }
        }
        InitSmoothMovement();
    }

    // ==================== Trajectory Recording ====================

    private void RecordTrajectories()
    {
        for (int i = 0; i < 4; i++)
        {
            var drone = Swarm_Drone_Organizer.Instance.swarmDrones[i];
            if (drone.controller == null) continue;

            Vector3 pos = drone.controller.transform.position;
            if (droneTrajectories[i].Count == 0 || Vector3.Distance(droneTrajectories[i].Last(), pos) > 0.5f)
            {
                droneTrajectories[i].Add(pos);
                trajectoryRenderers[i].positionCount = droneTrajectories[i].Count;
                trajectoryRenderers[i].SetPositions(droneTrajectories[i].ToArray());
            }
        }
    }

    // ==================== Phase 1: Lane Calculation ====================

    private void CalculateLanes()
    {
        float minX = areaCorners.Min(c => c.x);
        float maxX = areaCorners.Max(c => c.x);
        float minZ = areaCorners.Min(c => c.y);
        float maxZ = areaCorners.Max(c => c.y);
        float laneWidth = (maxX - minX) / 4f;

        // Number of points to sample along the length of each lane
        int rows = Mathf.Max(phase1WaypointsPerLane, 10);
        float rowSpacing = (maxZ - minZ) / Mathf.Max(rows - 1, 1);

        for (int i = 0; i < 4; i++)
        {
            droneWaypoints[i] = new List<Vector3>();

            // Phase 1: 4 straight lanes (one for each drone)
            float laneCenterX = minX + (i * laneWidth) + (laneWidth / 2f);
            
            for (int r = 0; r < rows; r++)
            {
                float t = (float)r / (rows - 1);
                float laneZ = Mathf.Lerp(minZ, maxZ, t);
                droneWaypoints[i].Add(new Vector3(laneCenterX, phase1Altitude, laneZ));
            }
        }
    }

    private List<Vector3> GenerateQuadrantWaypoints(int droneIdx, float minX, float maxX, float minZ, float maxZ, float altitude)
    {
        List<Vector3> points = new List<Vector3>();
        float midX = (minX + maxX) / 2f;
        float midZ = (minZ + maxZ) / 2f;
        float overlapBuffer = 3f;

        Vector2 qMin, qMax;
        switch(droneIdx)
        {
            case 2: qMin = new Vector2(minX, midZ + overlapBuffer); qMax = new Vector2(midX - overlapBuffer, maxZ); break;
            case 3: qMin = new Vector2(midX + overlapBuffer, midZ + overlapBuffer); qMax = new Vector2(maxX, maxZ); break;
            default: return points;
        }

        int rows = phase2SweepRows;
        float rowSpacing = (qMax.y - qMin.y) / Mathf.Max(rows - 1, 1);
        for (int r = 0; r < rows; r++)
        {
            float z = qMax.y - r * rowSpacing;
            float x1 = qMin.x; float x2 = qMax.x;
            points.Add(new Vector3((r % 2 == 0) ? x1 : x2, altitude, z));
            points.Add(new Vector3((r % 2 == 0) ? x2 : x1, altitude, z));
        }
        return points;
    }

    // ==================== Phase 2: Quadrant Calculation ====================

    private void CalculateQuadrants()
    {
        float minX = areaCorners.Min(c => c.x);
        float maxX = areaCorners.Max(c => c.x);
        float minZ = areaCorners.Min(c => c.y);
        float maxZ = areaCorners.Max(c => c.y);

        // If we received custom zones via HTTP, use them instead of default split
        if (receivedPhase2Zones != null && receivedPhase2Zones.Length == 4)
        {
            Debug.Log("[Scouting] Using custom Phase 2 zones from HTTP.");
            for (int i = 0; i < 4; i++)
            {
                var z = receivedPhase2Zones[i];
                Vector2 qMin = new Vector2(z.minX, z.minZ);
                Vector2 qMax = new Vector2(z.maxX, z.maxZ);
                
                // Determine start directions intelligently or just use defaults
                bool sAtMinX = (i % 2 == 0);
                bool sAtMinZ = (i < 2);
                
                droneWaypoints[i] = GenerateSerpentine(qMin, qMax, phase2Altitude, phase2SweepRows, sAtMinX, sAtMinZ);
                ValidateWaypoints(droneWaypoints[i]);
            }
            return;
        }

        float midX = (minX + maxX) / 2f;
        float midZ = (minZ + maxZ) / 2f;
        float overlapBuffer = 3f;

        Vector2[] quadrantMins = {
            new Vector2(minX, minZ),
            new Vector2(midX + overlapBuffer, minZ),
            new Vector2(minX, midZ + overlapBuffer),
            new Vector2(midX + overlapBuffer, midZ + overlapBuffer)
        };
        Vector2[] quadrantMaxs = {
            new Vector2(midX - overlapBuffer, midZ - overlapBuffer),
            new Vector2(maxX, midZ - overlapBuffer),
            new Vector2(midX - overlapBuffer, maxZ),
            new Vector2(maxX, maxZ)
        };

        // Define which corner of the quadrant is the "outer" corner of the whole area
        bool[] startAtMinX = { true, false, true, false };
        bool[] startAtMinZ = { true, true, false, false };

        for (int i = 0; i < 4; i++)
        {
            droneWaypoints[i] = GenerateSerpentine(quadrantMins[i], quadrantMaxs[i], phase2Altitude, phase2SweepRows, startAtMinX[i], startAtMinZ[i]);
            ValidateWaypoints(droneWaypoints[i]);
        }
    }

    private List<Vector3> GenerateSerpentine(Vector2 min, Vector2 max, float altitude, int rows, bool startAtMinX = true, bool startAtMinZ = true)
    {
        List<Vector3> points = new List<Vector3>();
        float rowSpacing = (max.y - min.y) / Mathf.Max(rows - 1, 1);

        for (int r = 0; r < rows; r++)
        {
            // If starting at MinZ, r=0 is MinZ. If starting at MaxZ, r=0 is MaxZ.
            float z = startAtMinZ ? (min.y + r * rowSpacing) : (max.y - r * rowSpacing);

            // Alternate X direction. 
            // If r%2 == 0, use startX. If r%2 == 1, use endX.
            float x1 = startAtMinX ? min.x : max.x;
            float x2 = startAtMinX ? max.x : min.x;

            if (r % 2 == 0)
            {
                float y1 = RobustSampleGroundHeight(x1, z) + altitude;
                float y2 = RobustSampleGroundHeight(x2, z) + altitude;
                points.Add(new Vector3(x1, y1, z));
                points.Add(new Vector3(x2, y2, z));
            }
            else
            {
                float y1 = RobustSampleGroundHeight(x2, z) + altitude;
                float y2 = RobustSampleGroundHeight(x1, z) + altitude;
                points.Add(new Vector3(x2, y1, z));
                points.Add(new Vector3(x1, y2, z));
            }
        }

        SmoothWaypointHeights(points);
        return points;
    }

    private float SampleGroundHeight(float x, float z)
    {
        Vector3 origin = new Vector3(x, raycastOriginHeight, z);
        if (Physics.Raycast(origin, Vector3.down, out RaycastHit hit, raycastOriginHeight * 2f, groundLayer))
            return hit.point.y;
        return 0f;
    }

    /// <summary>
    /// Samples ground height at multiple points around the target to avoid "missing" building edges.
    /// </summary>
    private float RobustSampleGroundHeight(float x, float z, float customOffset = -1f)
    {
        float maxH = 0f;
        float offset = customOffset > 0 ? customOffset : 0.5f;
        Vector2[] samples = {
            new Vector2(x, z),
            new Vector2(x + offset, z),
            new Vector2(x - offset, z),
            new Vector2(x, z + offset),
            new Vector2(x, z - offset)
        };

        foreach (var s in samples)
        {
            maxH = Mathf.Max(maxH, SampleGroundHeight(s.x, s.y));
        }

        // If all samples are 0 (likely off-map), fallback to a sensible baseline
        if (maxH <= 0.01f)
        {
            // Use area center height as fallback
            return areaCenter.y - phase1Altitude;
        }

        return maxH;
    }

    /// <summary>
    /// Applies a simple smoothing pass to the Y coordinates of waypoints to prevent sharp jumps.
    /// </summary>
    private void SmoothWaypointHeights(List<Vector3> waypoints)
    {
        if (waypoints.Count < 3) return;

        Vector3[] original = waypoints.ToArray();
        for (int i = 1; i < original.Length - 1; i++)
        {
            // Simple moving average (1-2-1 weighted)
            float smoothY = (original[i - 1].y + original[i].y * 2f + original[i + 1].y) / 4f;
            waypoints[i] = new Vector3(original[i].x, smoothY, original[i].z);
        }
    }

    [Header("Waypoint Safety")]
    [Tooltip("Radius to check for obstacles around each waypoint")]
    public float clearanceRadius = 2f;
    [Tooltip("How much to raise a waypoint each step if blocked")]
    public float clearanceStep = 1f;
    [Tooltip("Max times to raise a waypoint before giving up")]
    public int maxClearanceAttempts = 20;

    /// <summary>
    /// Checks if a waypoint collides with anything and pushes it up until clear.
    /// </summary>
    private Vector3 EnsureClearance(Vector3 point)
    {
        for (int attempt = 0; attempt < maxClearanceAttempts; attempt++)
        {
            Collider[] hits = Physics.OverlapSphere(point, clearanceRadius, groundLayer);

            bool foundRealObstacle = false;
            foreach (var h in hits)
            {
                // Filter out drones/players so the drone doesn't detect itself
                if (!h.isTrigger && !h.CompareTag("Player") && !h.name.ToLower().Contains("drone"))
                {
                    foundRealObstacle = true;
                    break;
                }
            }

            if (!foundRealObstacle)
                return point;

            point.y += clearanceStep;
        }
        Debug.LogWarning($"[Scouting] Waypoint at ({point.x}, {point.z}) could not find clearance after {maxClearanceAttempts} attempts. Using Y={point.y}");
        return point;
    }

    /// <summary>
    /// Post-processes a waypoint list to ensure all points have terrain clearance.
    /// </summary>
    private void ValidateWaypoints(List<Vector3> waypoints)
    {
        for (int i = 0; i < waypoints.Count; i++)
        {
            waypoints[i] = EnsureClearance(waypoints[i]);
        }
    }

    // ==================== Gizmos ====================

    void OnDrawGizmos()
    {
        if (areaCorners == null || areaCorners.Length != 4) return;

        Gizmos.color = Color.yellow;
        for (int i = 0; i < 4; i++)
        {
            Vector3 start = new Vector3(areaCorners[i].x, phase1Altitude, areaCorners[i].y);
            Vector3 end = new Vector3(areaCorners[(i + 1) % 4].x, phase1Altitude, areaCorners[(i + 1) % 4].y);
            Gizmos.DrawLine(start, end);
        }

        if (droneWaypoints != null)
        {
            for (int i = 0; i < droneWaypoints.Length; i++)
            {
                if (droneWaypoints[i] == null) continue;
                Gizmos.color = droneColors[i];
                float displayY = (i < 2 && currentState == MissionState.P1_SCOUTING) ? phase1Altitude : phase2Altitude;
                if (currentState == MissionState.IDLE) displayY = phase1Altitude;

                for (int j = 0; j < droneWaypoints[i].Count - 1; j++)
                {
                    Vector3 p1 = droneWaypoints[i][j];
                    Vector3 p2 = droneWaypoints[i][j + 1];
                    // Flatten for Gizmo display
                    p1.y = displayY;
                    p2.y = displayY;
                    Gizmos.DrawLine(p1, p2);
                }
                foreach (var wp in droneWaypoints[i])
                {
                    Vector3 flatWp = wp;
                    flatWp.y = displayY;
                    Gizmos.DrawWireSphere(flatWp, 0.3f);
                }
            }
        }

        // Draw Active A* Paths
        if (activeAStarPaths != null)
        {
            for (int i = 0; i < activeAStarPaths.Length; i++)
            {
                if (activeAStarPaths[i] == null) continue;
                Gizmos.color = new Color(droneColors[i].r, droneColors[i].g, droneColors[i].b, 0.5f);
                for (int j = 0; j < activeAStarPaths[i].Count - 1; j++)
                {
                    Gizmos.DrawLine(activeAStarPaths[i][j], activeAStarPaths[i][j + 1]);
                    Gizmos.DrawSphere(activeAStarPaths[i][j], 0.1f);
                }
            }
        }
    }
}
