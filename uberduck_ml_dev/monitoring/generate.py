__all__ = []


from ..data_loader import prepare_input_sequence


def _get_inference(model, vocoder, texts, speaker_ids, symbol_set, arpabet, cpu_run):

    text_padded, input_lengths = prepare_input_sequence(
        texts, cpu_run=cpu_run, arpabet=arpabet, symbol_set=symbol_set
    )
    # Note (SAM): None is for GST... temporary solution
    input_ = text_padded, input_lengths, speaker_ids, None
    output = model.inference(input_)
    audio = vocoder.infer(output[1][:1])
    return audio
