using UnityEngine;

/// <summary>
/// Battery sensor class to simulate power consumption.
/// </summary>
public class Battery : MonoBehaviour {

    [Header("Battery Settings")]
    [Tooltip("Maximum battery capacity in units.")]
    public float capacity = 100f;
    
    [Tooltip("Base drain rate per second.")]
    public float drainRate = 0.1f;

    [Header("Current State")]
    public float currentLevel;

    /// <summary>
    /// Gets the current battery percentage (0 to 1).
    /// </summary>
    /// <returns></returns>
    public float getBatteryPercentage() {
        return capacity > 0 ? currentLevel / capacity : 0f;
    }

    void Awake() {
        currentLevel = capacity;
    }

    void Update() {
        if (currentLevel > 0) {
            currentLevel -= drainRate * Time.deltaTime;
            currentLevel = Mathf.Max(currentLevel, 0f);
        }
    }
}
