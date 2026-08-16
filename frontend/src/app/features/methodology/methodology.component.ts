import { Component } from '@angular/core';
import { FlowDiagramComponent } from './flow-diagram/flow-diagram.component';

@Component({
  selector: 'app-methodology',
  standalone: true,
  imports: [FlowDiagramComponent],
  templateUrl: './methodology.component.html',
  styleUrl: './methodology.component.css'
})
export class MethodologyComponent {}
