# Copyright 2021 Sony Semiconductor Israel, Inc. All rights reserved.
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
import model_compression_toolkit.gptq.common.gptq_config
from model_compression_toolkit.core.tpc_models.default_tpc.latest import generate_keras_tpc
from model_compression_toolkit.core.keras.default_framework_info import DEFAULT_KERAS_INFO
import tensorflow as tf
import numpy as np
import unittest
import model_compression_toolkit as mct
from model_compression_toolkit.gptq.keras.gptq_loss import multiple_tensors_mse_loss
from tests.common_tests.helpers.generate_test_tp_model import generate_test_tp_model
from tests.keras_tests.tpc_keras import get_16bit_tpc
from tests.common_tests.helpers.tensors_compare import cosine_similarity
from enum import Enum
import random

keras = tf.keras
layers = keras.layers
tp = mct.target_platform

QUANTIZATION_CONFIG = mct.QuantizationConfig(activation_error_method=mct.QuantizationErrorMethod.MSE,
                                             weights_error_method=mct.QuantizationErrorMethod.MSE,
                                             relu_bound_to_power_of_2=False, weights_bias_correction=False,
                                             weights_per_channel_threshold=True)

TWO_BIT_QUANTIZATION = generate_keras_tpc(name="two_bit_network_test",
                                          tp_model=generate_test_tp_model({'weights_n_bits': 2,
                                                                           'activation_n_bits': 2}))

EIGHT_BIT_QUANTIZATION = generate_keras_tpc(name="eight_bit_network_test",
                                            tp_model=generate_test_tp_model({'weights_n_bits': 8,
                                                                             'activation_n_bits': 8}))

FLOAT_QUANTIZATION = get_16bit_tpc("float_network_test")


class RunMode(Enum):
    TWO = 0
    EIGHT = 1
    FLOAT = 2


def run_mode(tpc):
    if tpc is FLOAT_QUANTIZATION:
        return RunMode.FLOAT
    elif tpc is EIGHT_BIT_QUANTIZATION:
        return RunMode.EIGHT
    else:
        return RunMode.TWO


class NetworkTest(object):
    def __init__(self, unit_test, model_float, input_shapes, num_calibration_iter, gptq=False):
        self.unit_test = unit_test
        self.model_float = model_float
        self.input_shapes = input_shapes
        self.num_calibration_iter = num_calibration_iter
        self.gptq = gptq

    def compare(self, inputs_list, quantized_model, qc, tpc):
        output_q = quantized_model.predict(inputs_list)
        output_f = self.model_float.predict(inputs_list)
        if isinstance(output_f, list):
            cs = np.mean([cosine_similarity(oq, of) for oq, of, in zip(output_q, output_f)])
        else:
            cs = cosine_similarity(output_f, output_q)
        if run_mode(tpc) == RunMode.FLOAT:
            self.unit_test.assertTrue(np.isclose(cs, 1, 0.001), msg=f'fail cosine similarity check: {cs}')
        elif run_mode(tpc) == RunMode.EIGHT:
            pass  # remove the cs check for 8 bit quantizaiton at this stage
            # self.unit_test.assertTrue(np.isclose(cs, 1, atol=0.6), msg=f'fail cosine similarity check:{cs}')
        elif run_mode(tpc) == RunMode.TWO:
            self.unit_test.assertTrue(np.isclose(cs, 0, atol=0.5), msg=f'fail cosine similarity check:{cs}')
        if run_mode(tpc) == RunMode.EIGHT:
            # TFLite Converter only support eight bit quantization
            try:
                converter = tf.lite.TFLiteConverter.from_keras_model(quantized_model)
                converter.convert()
            except Exception as e:
                error_msg = e.message if hasattr(e, 'message') else str(e)
                self.unit_test.assertTrue(False, f'fail TFLite convertion with the following error: {error_msg}')

    def run_network(self, inputs_list, qc, tpc):
        def representative_data_gen():
            return inputs_list

        if self.gptq:
            arc = model_compression_toolkit.gptq.common.gptq_config.GradientPTQConfig(n_iter=2,
                                                                                      optimizer=tf.keras.optimizers.Adam(
                                                                                          learning_rate=0.0001),
                                                                                      optimizer_rest=tf.keras.optimizers.Adam(
                                                                                          learning_rate=0.0001),
                                                                                      loss=multiple_tensors_mse_loss)

            ptq_model, quantization_info = mct.keras_post_training_quantization(self.model_float,
                                                                                representative_data_gen,
                                                                                quant_config=qc,
                                                                                fw_info=DEFAULT_KERAS_INFO,
                                                                                n_iter=self.num_calibration_iter,
                                                                                gptq_config=arc,
                                                                                target_platform_capabilities=tpc)
        else:
            ptq_model, quantization_info = mct.keras_post_training_quantization(self.model_float,
                                                                                representative_data_gen,
                                                                                quant_config=qc,
                                                                                fw_info=DEFAULT_KERAS_INFO,
                                                                                n_iter=self.num_calibration_iter,
                                                                                target_platform_capabilities=tpc)
        self.compare(inputs_list, ptq_model, qc, tpc)


def set_seed():
    print("Setting initial seed... ")
    np.random.seed(1)
    random.seed(1)
    tf.random.set_seed(1)


class FeatureNetworkTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        set_seed()

    @staticmethod
    def create_inputs(inputs_list):
        return [np.random.randn(*in_shape) for in_shape in inputs_list]

    def run_network(self, model_float, input_shapes, num_calibration_iter, gptq=False):
        inputs_list = FeatureNetworkTest.create_inputs(input_shapes)

        NetworkTest(self, model_float, input_shapes, num_calibration_iter, gptq=gptq).run_network(inputs_list,
                                                                                                  QUANTIZATION_CONFIG,
                                                                                                  EIGHT_BIT_QUANTIZATION)
        if not gptq:
            NetworkTest(self, model_float, input_shapes, num_calibration_iter, gptq=gptq).run_network(inputs_list,
                                                                                                      QUANTIZATION_CONFIG,
                                                                                                      TWO_BIT_QUANTIZATION)
            NetworkTest(self, model_float, input_shapes, num_calibration_iter, gptq=gptq).run_network(inputs_list,
                                                                                                      QUANTIZATION_CONFIG,
                                                                                                      FLOAT_QUANTIZATION)

    def test_mobilenet_v1(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.mobilenet import MobileNet
        self.run_network(MobileNet(), input_shapes, num_calibration_iter)

    def test_mobilenet_v1_gptq(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.mobilenet import MobileNet
        self.run_network(MobileNet(), input_shapes, num_calibration_iter, gptq=True)

    def test_mobilenet_v2(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2
        self.run_network(MobileNetV2(), input_shapes, num_calibration_iter)

    def test_xception(self):
        input_shapes = [[10, 299, 299, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.xception import Xception
        self.run_network(Xception(), input_shapes, num_calibration_iter)

    def test_resnet(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.resnet import ResNet50
        self.run_network(ResNet50(), input_shapes, num_calibration_iter)

    def test_efficientnetbo(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.efficientnet import EfficientNetB0
        self.run_network(EfficientNetB0(), input_shapes, num_calibration_iter)

    def test_nasnetmobile(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.nasnet import NASNetMobile
        self.run_network(NASNetMobile(), input_shapes, num_calibration_iter)

    def test_resnetv2(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.resnet_v2 import ResNet50V2
        self.run_network(ResNet50V2(), input_shapes, num_calibration_iter)

    def test_densenet121(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.densenet import DenseNet121
        self.run_network(DenseNet121(), input_shapes, num_calibration_iter)

    def test_vgg(self):
        input_shapes = [[10, 224, 224, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.vgg16 import VGG16
        self.run_network(VGG16(), input_shapes, num_calibration_iter)

    def test_inceptionresnet(self):
        input_shapes = [[10, 299, 299, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.inception_resnet_v2 import InceptionResNetV2
        self.run_network(InceptionResNetV2(), input_shapes, num_calibration_iter)

    def test_inception(self):
        input_shapes = [[10, 299, 299, 3]]
        num_calibration_iter = 1
        from tensorflow.keras.applications.inception_v3 import InceptionV3
        self.run_network(InceptionV3(), input_shapes, num_calibration_iter)


if __name__ == '__main__':
    unittest.main()
