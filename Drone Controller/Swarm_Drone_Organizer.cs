using UnityEngine;
using System;
using System.Collections.Generic;

[Serializable]
public class SwarmDrone
{
    public string droneId;
    public droneMovementController controller;
    public GPS gps;
    public Barometer barometer;
    public Transform singlePoint;

    [Tooltip("Offset relative to the swarm center position")]
    public Vector3 localOffset;

    [Header("Current Status (Read Only)")]
    public Vector2 currentGpsPos;
    public float currentAltitude;
}

public enum SwarmFormation { Square, Diamond, Line }

public class Swarm_Drone_Organizer : MonoBehaviour
{
    public static Swarm_Drone_Organizer Instance { get; private set; }

    [Header("Swarm Configuration")]
    public List<SwarmDrone> swarmDrones = new List<SwarmDrone>();
    
    [Header("Formation Settings")]
    public SwarmFormation currentFormation = SwarmFormation.Square;
    public float spacing = 5f;
    public bool autoRecalculate = true;

    [Header("Current Swarm Target")]
    public Vector3 swarmCenterTarget;

    void Awake()
    {
        if (Instance == null) Instance = this;
        else Destroy(gameObject);
    }

    void OnValidate()
    {
        if (autoRecalculate) CalculateFormationOffsets();
    }

    [ContextMenu("Recalculate Offsets")]
    public void CalculateFormationOffsets()
    {
        int count = swarmDrones.Count;
        if (count == 0) return;

        for (int i = 0; i < count; i++)
        {
            Vector3 offset = Vector3.zero;
            switch (currentFormation)
            {
                case SwarmFormation.Square:
                    // 4 drones pattern: (-s,0,-s), (s,0,-s), (-s,0,s), (s,0,s)
                    float s = spacing / 2f;
                    offset = new Vector3((i % 2 == 0 ? -s : s), 0, (i < 2 ? -s : s));
                    break;
                case SwarmFormation.Diamond:
                    // 4 drones pattern: (s,0,0), (-s,0,0), (0,0,s), (0,0,-s)
                    if (i == 0) offset = new Vector3(spacing, 0, 0);
                    else if (i == 1) offset = new Vector3(-spacing, 0, 0);
                    else if (i == 2) offset = new Vector3(0, 0, spacing);
                    else if (i == 3) offset = new Vector3(0, 0, -spacing);
                    break;
                case SwarmFormation.Line:
                    // Horizontal line centered at 0
                    float totalWidth = (count - 1) * spacing;
                    offset = new Vector3(-totalWidth / 2f + (i * spacing), 0, 0);
                    break;
            }
            swarmDrones[i].localOffset = offset;
        }
    }

    void Update()
    {
        // Update current status for visibility in inspector
        foreach (var drone in swarmDrones)
        {
            if (drone.gps != null)
            {
                drone.currentGpsPos = drone.gps.getCoords();
            }
            if (drone.barometer != null)
            {
                drone.currentAltitude = drone.barometer.getHeight();
            }
        }
    }

    /// <summary>
    /// Commands the entire swarm to move to a new world position.
    /// Each drone will maintain its local offset relative to this center point.
    /// </summary>
    /// <param name="centerPosition">The target world position for the swarm center</param>
    public void SetSwarmTarget(Vector3 centerPosition)
    {
        swarmCenterTarget = centerPosition;
        
        for (int i = 0; i < swarmDrones.Count; i++)
        {
            SetDroneTarget(i, centerPosition + swarmDrones[i].localOffset);
        }
    }

    /// <summary>
    /// Commands a specific drone to move to a target position by moving its singlePoint object.
    /// </summary>
    /// <param name="index">Index of the drone in the swarm list</param>
    /// <param name="target">World position target</param>
    public void SetDroneTarget(int index, Vector3 target)
    {
        if (index < 0 || index >= swarmDrones.Count) return;
        
        var drone = swarmDrones[index];
        if (drone.singlePoint != null)
        {
            drone.singlePoint.position = target;
        }
    }

    /// <summary>
    /// Example method to move to a position called via a key or external script
    /// </summary>
    [ContextMenu("Send Swarm to Current Center Target")]
    public void ExecuteSwarmMove()
    {
        SetSwarmTarget(swarmCenterTarget);
    }
    
    /// <summary>
    /// Helper to visualize the relative offsets in the inspector coordinate system
    /// </summary>
    void OnDrawGizmosSelected()
    {
        Gizmos.color = Color.cyan;
        Gizmos.DrawWireSphere(swarmCenterTarget, 0.5f);
        
        foreach (var drone in swarmDrones)
        {
            Gizmos.DrawLine(swarmCenterTarget, swarmCenterTarget + drone.localOffset);
            Gizmos.DrawWireSphere(swarmCenterTarget + drone.localOffset, 0.3f);
        }
    }
}
