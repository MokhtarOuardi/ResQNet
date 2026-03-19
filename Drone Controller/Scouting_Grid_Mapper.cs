using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System.Linq;

public class Scouting_Grid_Mapper : MonoBehaviour
{
    public static Scouting_Grid_Mapper Instance { get; private set; }

    [Header("Grid Configuration")]
    public float cellSize = 2f;
    public float obstacleHeightThreshold = 1.5f; // If ground height - cell height > this, mark as obstacle
    public LayerMask mappingLayer = -1;
    public float raycastHeight = 100f;

    [Header("A* Settings")]
    public bool allowDiagonal = true;
    public int maxPathNodes = 500;
    [Tooltip("Number of cells to keep clear around the drone horizontally")]
    public int horizontalSafetyBuffer = 1;

    private float[,] heightMap;
    private bool[,] occupancyMap;
    private bool[,] mappedCells; // To track what has been "scanned"
    
    private Vector2 gridOrigin;
    private int gridWidth, gridHeight;
    private float minX, minZ, maxX, maxZ;

    void Awake()
    {
        Instance = this;
    }

    public void InitializeGrid(Vector2[] corners)
    {
        minX = corners.Min(c => c.x);
        maxX = corners.Max(c => c.x);
        minZ = corners.Min(c => c.y);
        maxZ = corners.Max(c => c.y);

        gridWidth = Mathf.CeilToInt((maxX - minX) / cellSize);
        gridHeight = Mathf.CeilToInt((maxZ - minZ) / cellSize);
        gridOrigin = new Vector2(minX, minZ);

        heightMap = new float[gridWidth, gridHeight];
        occupancyMap = new bool[gridWidth, gridHeight];
        mappedCells = new bool[gridWidth, gridHeight];

        Debug.Log($"[GridMapper] Initialized {gridWidth}x{gridHeight} grid at {gridOrigin}");
    }

    public void UpdateMap(Vector3 scanPosition, float scanRadius)
    {
        int centerX, centerZ;
        WorldToGrid(scanPosition, out centerX, out centerZ);

        int cellRadius = Mathf.CeilToInt(scanRadius / cellSize);
        
        // Start raycast slightly below the drone to avoid hitting itself
        float safeRayStart = scanPosition.y - 1f;

        for (int x = centerX - cellRadius; x <= centerX + cellRadius; x++)
        {
            for (int z = centerZ - cellRadius; z <= centerZ + cellRadius; z++) // Corrected loop
            {
                if (IsInGrid(x, z))
                {
                    Vector3 worldPos = GridToWorld(x, z);
                    float dist = Vector2.Distance(new Vector2(scanPosition.x, scanPosition.z), new Vector2(worldPos.x, worldPos.z));
                    
                    if (dist <= scanRadius)
                    {
                        UpdateCell(x, z, safeRayStart);
                    }
                }
            }
        }
    }

    private void UpdateCell(int x, int z, float rayStartH)
    {
        Vector3 worldPos = GridToWorld(x, z);
        Vector3 rayStart = new Vector3(worldPos.x, rayStartH, worldPos.z);

        // Raycast down from drone level. Filter out drone self-hits.
        RaycastHit[] hits = Physics.RaycastAll(rayStart, Vector3.down, 200f, mappingLayer);
        foreach (var hit in hits)
        {
            if (hit.distance > 0.1f)
            {
                heightMap[x, z] = hit.point.y;
                mappedCells[x, z] = true;
                break;
            }
        }
    }

    public List<Vector3> FindPath(Vector3 start, Vector3 end, float flyAltitude)
    {
        int startX, startZ, endX, endZ;
        WorldToGrid(start, out startX, out startZ);
        WorldToGrid(end, out endX, out endZ);

        if (!IsInGrid(startX, startZ) || !IsInGrid(endX, endZ)) return null;

        Node startNode = new Node(startX, startZ);
        Node endNode = new Node(endX, endZ);

        List<Node> openSet = new List<Node> { startNode };
        HashSet<string> closedSet = new HashSet<string>();
        Dictionary<string, Node> allNodes = new Dictionary<string, Node>();
        allNodes[startNode.Id] = startNode;

        int iterations = 0;
        while (openSet.Count > 0 && iterations < maxPathNodes)
        {
            iterations++;
            Node current = openSet.OrderBy(n => n.fCost).First();

            if (current.x == endNode.x && current.z == endNode.z)
            {
                return RetracePath(current, flyAltitude);
            }

            openSet.Remove(current);
            closedSet.Add(current.Id);

            foreach (Node neighbor in GetNeighbors(current))
            {
                if (closedSet.Contains(neighbor.Id)) continue;
                
                // Obstacle check: check neighbors in a radius for better clearance
                bool isBlocked = false;
                for (int nx = -horizontalSafetyBuffer; nx <= horizontalSafetyBuffer; nx++)
                {
                    for (int nz = -horizontalSafetyBuffer; nz <= horizontalSafetyBuffer; nz++)
                    {
                        int checkX = neighbor.x + nx;
                        int checkZ = neighbor.z + nz;
                        if (IsInGrid(checkX, checkZ) && mappedCells[checkX, checkZ])
                        {
                            if (heightMap[checkX, checkZ] > flyAltitude - 1f) // Increased buffer
                            {
                                isBlocked = true;
                                break;
                            }
                        }
                    }
                    if (isBlocked) break;
                }

                if (isBlocked) continue;

                float newMovementCost = current.gCost + GetDistance(current, neighbor);
                string nId = neighbor.Id;

                if (!allNodes.ContainsKey(nId) || newMovementCost < allNodes[nId].gCost)
                {
                    neighbor.gCost = newMovementCost;
                    neighbor.hCost = GetDistance(neighbor, endNode);
                    neighbor.parent = current;

                    if (!openSet.Any(n => n.Id == nId))
                    {
                        openSet.Add(neighbor);
                        allNodes[nId] = neighbor;
                    }
                }
            }
        }

        return null;
    }

    private List<Vector3> RetracePath(Node endNode, float altitude)
    {
        List<Vector3> path = new List<Vector3>();
        Node current = endNode;
        while (current != null)
        {
            Vector3 worldPos = GridToWorld(current.x, current.z);
            // Fallback for unmapped cells to prevent diving
            float groundY = mappedCells[current.x, current.z] ? heightMap[current.x, current.z] : 0;
            path.Add(new Vector3(worldPos.x, groundY + altitude, worldPos.z));
            current = current.parent;
        }
        path.Reverse();

        // --- Altitude Smoothing (Early Climb) ---
        // Prevents sharp vertical jumps by starting the climb several nodes early
        int lookahead = 6; 
        for (int i = 0; i < path.Count - 1; i++)
        {
            float maxFutureY = path[i].y;
            for (int j = i + 1; j <= Mathf.Min(i + lookahead, path.Count - 1); j++)
            {
                maxFutureY = Mathf.Max(maxFutureY, path[j].y);
            }

            if (maxFutureY > path[i].y)
            {
                // Gradually slope up!
                float diff = maxFutureY - path[i].y;
                path[i] = new Vector3(path[i].x, path[i].y + diff * 0.4f, path[i].z);
            }
        }

        // Final smoothing pass
        for (int i = 1; i < path.Count - 1; i++)
        {
            float smoothY = (path[i - 1].y + path[i].y + path[i + 1].y) / 3f;
            path[i] = new Vector3(path[i].x, smoothY, path[i].z);
        }

        return path;
    }

    private IEnumerable<Node> GetNeighbors(Node node)
    {
        for (int x = -1; x <= 1; x++)
        {
            for (int z = -1; z <= 1; z++)
            {
                if (x == 0 && z == 0) continue;
                if (!allowDiagonal && (Mathf.Abs(x) + Mathf.Abs(z) == 2)) continue;

                int nx = node.x + x;
                int nz = node.z + z;

                if (IsInGrid(nx, nz))
                    yield return new Node(nx, nz);
            }
        }
    }

    private float GetDistance(Node a, Node b)
    {
        int dstX = Mathf.Abs(a.x - b.x);
        int dstZ = Mathf.Abs(a.z - b.z);

        if (dstX > dstZ)
            return 14 * dstZ + 10 * (dstX - dstZ);
        return 14 * dstX + 10 * (dstZ - dstX);
    }

    private void WorldToGrid(Vector3 worldPos, out int x, out int z)
    {
        x = Mathf.FloorToInt((worldPos.x - gridOrigin.x) / cellSize);
        z = Mathf.FloorToInt((worldPos.z - gridOrigin.y) / cellSize);
    }

    private Vector3 GridToWorld(int x, int z)
    {
        return new Vector3(
            gridOrigin.x + (x * cellSize) + (cellSize / 2f),
            0,
            gridOrigin.y + (z * cellSize) + (cellSize / 2f)
        );
    }

    private bool IsInGrid(int x, int z)
    {
        return x >= 0 && x < gridWidth && z >= 0 && z < gridHeight;
    }

    public float GetHeightAt(Vector3 worldPos)
    {
        int x, z;
        WorldToGrid(worldPos, out x, out z);
        if (IsInGrid(x, z) && mappedCells[x, z]) return heightMap[x, z];
        return 0f;
    }

    private class Node
    {
        public int x, z;
        public float gCost, hCost;
        public Node parent;
        public string Id => $"{x}_{z}";
        public float fCost => gCost + hCost;

        public Node(int x, int z) { this.x = x; this.z = z; }
    }

    void OnDrawGizmos()
    {
        if (!Application.isPlaying || mappedCells == null) return;

        Gizmos.color = new Color(0, 1, 0, 0.2f);
        for (int x = 0; x < gridWidth; x++)
        {
            for (int z = 0; z < gridHeight; z++)
            {
                if (mappedCells[x, z])
                {
                    Vector3 pos = GridToWorld(x, z);
                    pos.y = heightMap[x, z];
                    Gizmos.DrawCube(pos, new Vector3(cellSize * 0.9f, 0.1f, cellSize * 0.9f));
                }
            }
        }
    }
}
