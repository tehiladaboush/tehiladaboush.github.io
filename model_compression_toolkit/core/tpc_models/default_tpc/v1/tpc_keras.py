# Copyright 2022 Sony Semiconductor Israel, Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import tensorflow as tf
from packaging import version

if version.parse(tf.__version__) < version.parse("2.6"):
    from tensorflow.keras.layers import Conv2D, DepthwiseConv2D, Reshape, ZeroPadding2D, \
        Dropout, \
        MaxPooling2D, Activation, ReLU, Flatten, Cropping2D
else:
    from keras.layers import Conv2D, DepthwiseConv2D, Reshape, ZeroPadding2D, \
        Dropout, MaxPooling2D, Activation, ReLU, Flatten, Cropping2D

from model_compression_toolkit.core.tpc_models.default_tpc.v1.tp_model import get_tp_model
import model_compression_toolkit as mct
from model_compression_toolkit.core.tpc_models.default_tpc.v1 import __version__ as TPC_VERSION

tp = mct.target_platform


def get_keras_tpc() -> tp.TargetPlatformCapabilities:
    """
    get a Keras TargetPlatformCapabilities object with default operation sets to layers mapping.
    Returns: a Keras TargetPlatformCapabilities object for the given TargetPlatformModel.
    """
    default_tp_model = get_tp_model()
    return generate_keras_tpc(name='default_keras_tpc', tp_model=default_tp_model)


def generate_keras_tpc(name: str, tp_model: tp.TargetPlatformModel):
    """
    Generates a TargetPlatformCapabilities object with default operation sets to layers mapping.

    Args:
        name: Name of the TargetPlatformCapabilities.
        tp_model: TargetPlatformModel object.

    Returns: a TargetPlatformCapabilities object for the given TargetPlatformModel.
    """

    keras_tpc = tp.TargetPlatformCapabilities(tp_model,
                                              name=name,
                                              version=TPC_VERSION)

    with keras_tpc:
        tp.OperationsSetToLayers("NoQuantization", [Reshape,
                                                    tf.reshape,
                                                    Flatten,
                                                    Cropping2D,
                                                    ZeroPadding2D,
                                                    Dropout,
                                                    MaxPooling2D,
                                                    tf.split,
                                                    tf.quantization.fake_quant_with_min_max_vars,
                                                    tf.math.argmax,
                                                    tf.shape,
                                                    tf.__operators__.getitem,
                                                    tf.compat.v1.shape])

        tp.OperationsSetToLayers("Conv", [Conv2D,
                                          DepthwiseConv2D,
                                          tf.nn.conv2d,
                                          tf.nn.depthwise_conv2d])
        tp.OperationsSetToLayers("AnyReLU", [tf.nn.relu,
                                             tf.nn.relu6,
                                             tp.LayerFilterParams(ReLU, negative_slope=0.0),
                                             tp.LayerFilterParams(Activation, activation="relu")])

    return keras_tpc
