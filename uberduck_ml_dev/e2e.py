__all__ = ["tts", "rhythm_transfer"]


import torch

from .text.symbols import NVIDIA_TACO2_SYMBOLS
from .text.util import text_to_sequence
from .data_loader import prepare_input_sequence


from typing import List

from .models.tacotron2 import Tacotron2
from .vocoders.hifigan import HiFiGanGenerator


def tts(
    lines: List[str],
    model,
    device: str,
    vocoder,
    arpabet=False,
    symbol_set=NVIDIA_TACO2_SYMBOLS,
    max_wav_value=32768.0,
    speaker_ids=None,
):
    assert isinstance(
        model, Tacotron2
    ), "Only Tacotron2 text-to-mel models are supported"
    assert isinstance(vocoder, HiFiGanGenerator), "Only Hifi GAN vocoders are supported"
    cpu_run = device == "cpu"
    sequences, input_lengths = prepare_input_sequence(
        lines, cpu_run=cpu_run, arpabet=arpabet, symbol_set=symbol_set
    )
    if speaker_ids is None:
        speaker_ids = torch.zeros(len(lines), dtype=torch.long, device=device)
    input_ = sequences, input_lengths, speaker_ids
    _, mel_outputs_postnet, gate_outputs, alignment, lengths = model.inference(input_)
    mels = mel_outputs_postnet
    mel = mels[0, :, : lengths[0].item()]
    for idx in range(1, mels.size(0)):
        length = lengths[idx].item()
        mel = torch.cat((mel, mels[idx, :, :length]), dim=-1)
    tensor_cls = torch.FloatTensor if device == "cpu" else torch.cuda.FloatTensor
    mel = mel[None, :]
    y_g_hat = vocoder(tensor_cls(mel).to(device=device))
    audio = y_g_hat.reshape(1, -1)
    audio = audio * max_wav_value
    return audio


from typing import Optional

from .models.common import MelSTFT


@torch.no_grad()
def rhythm_transfer(
    original_audio: torch.tensor,
    original_text: str,
    model,
    vocoder,
    device: str,
    symbol_set=NVIDIA_TACO2_SYMBOLS,
    arpabet=False,
    max_wav_value=32768.0,
    speaker_id=0,
):
    assert len(original_audio.shape) == 1
    cpu_run = device == "cpu"
    # TODO(zach): Support non-default STFT parameters.
    stft = MelSTFT()
    p_arpabet = float(arpabet)
    sequence, input_lengths, _ = prepare_input_sequence(
        [original_text], arpabet=arpabet, cpu_run=cpu_run, symbol_set=symbol_set
    )
    original_target_mel = stft.mel_spectrogram(original_audio[None])
    if not cpu_run:
        original_target_mel = original_target_mel.cuda()
    max_len = original_target_mel.size(2)
    speaker_ids = torch.tensor([speaker_id], dtype=torch.long, device=device)
    inputs = (
        sequence,
        input_lengths,
        original_target_mel,
        max_len,
        torch.tensor([max_len], dtype=torch.long, device=device),
        speaker_ids,
    )
    attn = model.get_alignment(inputs)
    _, mel_postnet, _, _ = model.inference_noattention(
        (sequence, input_lengths, speaker_ids, attn.transpose(0, 1))
    )
    y_g_hat = vocoder(torch.tensor(mel_postnet, dtype=torch.float, device=device))
    audio = y_g_hat.reshape(1, -1)
    audio = audio * max_wav_value
    return audio
