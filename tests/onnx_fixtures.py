"""Kleine ONNX-Policies für Tests (die echten liegen auf dem Hub)."""

import numpy as np


def linear_policy(path, weight=None, bias=None, recurrent=False, obs_len=61, act_len=14):
    """action = obs · W + b. recurrent=True: zusätzlich h_in/c_in → h_out/c_out (durchgereicht +1)."""
    import onnx
    from onnx import TensorProto, helper, numpy_helper

    w = np.zeros((obs_len, act_len), np.float32) if weight is None else np.asarray(weight, np.float32)
    b = np.zeros(act_len, np.float32) if bias is None else np.asarray(bias, np.float32)
    inputs = [helper.make_tensor_value_info("obs", TensorProto.FLOAT, ["batch", obs_len])]
    outputs = [helper.make_tensor_value_info("actions", TensorProto.FLOAT, ["batch", act_len])]
    nodes = [helper.make_node("MatMul", ["obs", "W"], ["xw"]), helper.make_node("Add", ["xw", "B"], ["actions"])]
    inits = [numpy_helper.from_array(w, "W"), numpy_helper.from_array(b, "B")]
    if recurrent:
        for n_in, n_out in (("h_in", "h_out"), ("c_in", "c_out")):
            inputs.append(helper.make_tensor_value_info(n_in, TensorProto.FLOAT, [1, 1, 8]))
            outputs.append(helper.make_tensor_value_info(n_out, TensorProto.FLOAT, [1, 1, 8]))
            nodes.append(helper.make_node("Add", [n_in, "one"], [n_out]))
        inits.append(numpy_helper.from_array(np.ones((1, 1, 8), np.float32), "one"))
    graph = helper.make_graph(nodes, "policy", inputs, outputs, inits)
    model = helper.make_model(graph, opset_imports=[helper.make_opsetid("", 17)])
    model.ir_version = 9
    onnx.save(model, str(path))
    return path
