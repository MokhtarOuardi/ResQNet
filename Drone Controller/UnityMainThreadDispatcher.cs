using UnityEngine;
using System.Collections;
using System.Collections.Generic;
using System;

public class UnityMainThreadDispatcher : MonoBehaviour {
    private static readonly Queue<Action> _executionQueue = new Queue<Action>();
    private static UnityMainThreadDispatcher _instance = null;

    public void Update() {
        lock (_executionQueue) {
            while (_executionQueue.Count > 0) {
                _executionQueue.Dequeue().Invoke();
            }
        }
    }

    public void Enqueue(Action action) {
        lock (_executionQueue) {
            _executionQueue.Enqueue(action);
        }
    }

    public static UnityMainThreadDispatcher Instance() {
        if (_instance == null) {
            GameObject go = new GameObject("UnityMainThreadDispatcher");
            _instance = go.AddComponent<UnityMainThreadDispatcher>();
            DontDestroyOnLoad(go);
        }
        return _instance;
    }
}
