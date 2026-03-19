using UnityEngine;
using System.Collections;

public class cameraBehaviour : MonoBehaviour {

    public Transform followThis;

    [Header("Swarm Follow Settings")]
    public bool followSwarm = true;
    public float minRadius = 10f;
    public float maxRadius = 100f;
    public float spreadMultiplier = 1.5f;

    [Header("Status & Settings")]
    public float radius = 20;
    public float angle = 0;
    public float turningSpeed = 5f;
    public float zoomSpeed = 10f;
    public float yOffset = 5f;
    public bool topDownMode = false;

    [Header("Cinematic Smoothing")]
    public float positionSmoothTime = 0.3f;
    public float focusSmoothTime = 0.15f;
    private Vector3 smoothedFocusPoint;
    private Vector3 posVelocity = Vector3.zero;
    private Vector3 focusVelocity = Vector3.zero;

    private Vector3 swarmCenter = Vector3.zero;

    KeyCode UP = KeyCode.Keypad8;
    KeyCode DW = KeyCode.Keypad2;
    KeyCode RI = KeyCode.Keypad6;
    KeyCode LE = KeyCode.Keypad4;
    KeyCode TOGGLE_TD = KeyCode.T;
    
    void Awake()
    {
        // Set initial smoothed focus point to current target
        smoothedFocusPoint = transform.position + transform.forward * 10f;

        // Find all cameras in the scene
        Camera[] allCams = Camera.allCameras;
        foreach (var cam in allCams)
        {
            if (cam.gameObject != gameObject)
            {
                // Remove MainCamera tag from other cameras to avoid confusion
                if (cam.CompareTag("MainCamera"))
                {
                    cam.tag = "Untagged";
                }
            }
        }

        // Set this camera as the MainCamera
        gameObject.tag = "MainCamera";
        
        Camera myCam = GetComponent<Camera>();
        if (myCam != null)
        {
            myCam.depth = 100;
            myCam.enabled = true;
            myCam.targetTexture = null;
        }
    }

    void LateUpdate()
    {
        Vector3 rawTargetPos = Vector3.zero;
        float spreadDist = 0;

        // 1. Calculate the raw swarm center and spread
        if (followSwarm && Swarm_Drone_Organizer.Instance != null && Swarm_Drone_Organizer.Instance.swarmDrones.Count > 0)
        {
            Vector3 sumPos = Vector3.zero;
            int activeCount = 0;
            foreach (var drone in Swarm_Drone_Organizer.Instance.swarmDrones)
            {
                if (drone.controller != null)
                {
                    sumPos += drone.controller.transform.position;
                    activeCount++;
                }
            }

            if (activeCount > 0)
            {
                swarmCenter = sumPos / activeCount;
                rawTargetPos = swarmCenter;

                // Calculate spread (max distance from center)
                float maxDist = 0;
                foreach (var drone in Swarm_Drone_Organizer.Instance.swarmDrones)
                {
                    if (drone.controller != null)
                    {
                        float d = Vector3.Distance(drone.controller.transform.position, swarmCenter);
                        if (d > maxDist) maxDist = d;
                    }
                }
                spreadDist = maxDist;
                
                // Auto-adjust radius based on spread
                float targetRadius = Mathf.Clamp(minRadius + spreadDist * spreadMultiplier, minRadius, maxRadius);
                radius = Mathf.Lerp(radius, targetRadius, Time.deltaTime * zoomSpeed * 0.2f);
            }
        }
        else if (followThis != null)
        {
            rawTargetPos = followThis.position;
        }

        if (rawTargetPos == Vector3.zero) return;

        // 2. Smooth the focus point (LookAt target) to eliminate drone jitter
        smoothedFocusPoint = Vector3.SmoothDamp(smoothedFocusPoint, rawTargetPos, ref focusVelocity, focusSmoothTime);

        // 3. Handle manual angle/radius controls
        if (Input.GetKey(LE)) angle -= turningSpeed * Time.deltaTime;
        if (Input.GetKey(RI)) angle += turningSpeed * Time.deltaTime;
        if (Input.GetKey(UP)) radius -= zoomSpeed * Time.deltaTime;
        if (Input.GetKey(DW)) radius += zoomSpeed * Time.deltaTime;
        if (Input.GetKeyDown(TOGGLE_TD)) topDownMode = !topDownMode;

        radius = Mathf.Clamp(radius, minRadius, maxRadius);

        // 4. Calculate desired camera position relative to the smoothed focus
        float x, y, z;
        if (topDownMode)
        {
            x = smoothedFocusPoint.x;
            y = smoothedFocusPoint.y + radius + yOffset + 10f; // Slightly higher for top-down
            z = smoothedFocusPoint.z;
        }
        else
        {
            x = Mathf.Cos(angle) * radius + smoothedFocusPoint.x;
            y = smoothedFocusPoint.y + radius / 1.5f + yOffset;
            z = Mathf.Sin(angle) * radius + smoothedFocusPoint.z;
        }
        Vector3 desiredCameraPos = new Vector3(x, y, z);

        // 5. Smoothly move camera towards desired position
        transform.position = Vector3.SmoothDamp(transform.position, desiredCameraPos, ref posVelocity, positionSmoothTime);
        
        // 6. Look at the smoothed focus point
        if (topDownMode)
        {
            // For top-down, we fix the UP vector to ensure it doesn't spin
            transform.LookAt(smoothedFocusPoint, Vector3.forward);
        }
        else
        {
            transform.LookAt(smoothedFocusPoint);
        }
    }


}
