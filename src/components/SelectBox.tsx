import type { ComponentProps } from 'react';
import Icon from './Icon';

export default function SelectBox(props: ComponentProps<'select'>) {
  return <span className="select-box">
    <select {...props}/>
    <Icon name="chevronDown" size={16}/>
  </span>;
}
